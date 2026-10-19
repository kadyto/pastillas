"""Transporte Android en proceso: SQLite local, sin sockets de escucha ni servidor.

Chaquopy llama a estas funciones directamente. Se reutilizan las operaciones de
la web mediante un adaptador de peticiones en memoria, nunca un servidor HTTP.
"""
import io
import json
import os
import re
import time
from email.message import Message
from pathlib import Path

from . import alerts, auth, inventory, medicine_info, service
from .db import connect, initialize as initialize_database
from .domain import Invalid, occurrences, zone
from .server import Handler, MAX_BODY

VERSION = '1.0.0'
MAX_IMPORT = 10 * 1024 * 1024


def initialize(directory, timezone='Europe/Madrid', version='1.0.0'):
    global VERSION
    VERSION = version
    target = Path(directory) / 'pastillas.sqlite'
    os.environ['DATABASE_PATH'] = str(target)
    initialize_database(target)
    try:
        zone(timezone)
    except Invalid:
        timezone = 'Europe/Madrid'
    with connect() as db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS android_settings (name TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS android_imports (digest TEXT PRIMARY KEY, imported_at INTEGER NOT NULL);
        ''')
        if not db.execute('SELECT 1 FROM users LIMIT 1').fetchone():
            # No hay cuenta remota ni contraseña: el almacenamiento es privado de Android.
            db.execute("INSERT INTO users(username,password,admin,timezone) VALUES('Mi botiquín','!local-only',1,?)", (timezone,))
        db.execute('UPDATE users SET ntfy_enabled=0')
    return str(target)


def local_user(db):
    return db.execute('SELECT * FROM users ORDER BY id LIMIT 1').fetchone()


def settings(db):
    stored = dict(db.execute('SELECT name,value FROM android_settings').fetchall())
    return dict(external_sources=stored.get('external_sources') == 'true')


class LocalRequest(Handler):
    def __init__(self, method, path, data):
        # BaseHTTPRequestHandler.__init__ no se invoca: no existe socket ni conexión.
        self.command, self.path, self.data = method, path, data
        self.client_address = ('local-android', 0)
        self.headers = Message()
        self.headers['Content-Type'] = 'application/json'
        self.rfile = io.BytesIO()
        self.response = dict(status=500, body=dict(error='No se pudo completar la operación local.'))

    def send(self, status, body, content_type=None, headers=None):
        self.response = dict(status=status, body=body)

    def body(self):
        return self.data

    def user(self, db):
        return local_user(db)

    def api(self, db, path, query):
        user, now = self.user(db), int(time.time())
        if path == '/api/session' and self.command == 'GET':
            if settings(db)['external_sources']:
                medicine_info.enqueue_user(db, user['id'], now)
                db.commit()
            return self.send(200, dict(user=auth.public_user(user), setup_required=False,
                                       version=VERSION, ntfy_base_url='', platform='android'))
        if path == '/api/version' and self.command == 'GET':
            return self.send(200, dict(installed_version=VERSION, state='android', update_available=False,
                                       deployment_configured=False, platform='android'))
        if path in ('/api/version/check', '/api/version/update', '/api/setup', '/api/login',
                    '/api/logout', '/api/password', '/api/users'):
            return self.send(400, dict(error='Esta función corresponde a la versión web. Android guarda el botiquín en el dispositivo.'))
        if path == '/api/android/settings':
            if self.command == 'GET':
                return self.send(200, settings(db))
            if self.command == 'PUT':
                enabled = self.data.get('external_sources')
                if type(enabled) is not bool:
                    raise Invalid('Selecciona si deseas consultar las fuentes externas.')
                db.execute('INSERT OR REPLACE INTO android_settings VALUES(?,?)',
                           ('external_sources', 'true' if enabled else 'false'))
                if enabled:
                    medicine_info.enqueue_user(db, user['id'], now)
                else:
                    db.execute('UPDATE medicine_cache SET pending=0 WHERE pending=1')
                db.commit()
                return self.send(200, settings(db))
        if path == '/api/android/erase' and self.command == 'POST':
            if self.data.get('confirm') != 'BORRAR':
                raise Invalid('Confirma el borrado del botiquín.')
            db.execute('BEGIN IMMEDIATE')
            for table in ('medications', 'prescriptions', 'alerts', 'medicine_cache', 'android_imports'):
                db.execute('DELETE FROM ' + table)
            db.execute("DELETE FROM android_settings WHERE name='external_sources'")
            db.commit()
            return self.send(200, dict(ok=True))
        if path == '/api/settings' and self.command == 'PUT':
            self.data = dict(self.data, ntfy_enabled=False, ntfy_topic='')
        remote = path in ('/api/medicine-search', '/api/medicine-catalog') or bool(re.fullmatch(
            r'/api/medications/\d+/(document|equivalents|information-check)', path)) or (
                self.command == 'POST' and bool(re.fullmatch(r'/api/medications/\d+/information', path)))
        if remote and not settings(db)['external_sources']:
            return self.send(409, dict(error='Activa «Consultar AEMPS y Vademécum» en Ajustes. Es opcional y necesita conexión a internet.'))
        return super().api(db, path, query)


def request(method, path, body=''):
    if method not in ('GET', 'POST', 'PUT', 'DELETE') or not isinstance(path, str) or not path.startswith('/api/') or len(path) > 4000:
        return json.dumps(dict(status=400, body=dict(error='Operación local no válida.')))
    try:
        if len(body.encode('utf-8')) > MAX_BODY:
            raise Invalid('El formulario es demasiado grande.')
        data = json.loads(body or '{}', parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if not isinstance(data, dict):
            raise Invalid('Formulario no válido.')
        handler = LocalRequest(method, path, data)
        handler.handle_request()
        return json.dumps(handler.response, ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError):
        return json.dumps(dict(status=400, body=dict(error='Formulario local no válido.')))


def export_json():
    with connect() as db:
        user = local_user(db)
        inventory.sync_due(db, user_id=user['id'])
        return json.dumps(service.export_data(db, user), ensure_ascii=False, allow_nan=False)


def import_json(raw):
    from .android_import import import_data
    if len(raw.encode('utf-8')) > MAX_IMPORT:
        raise Invalid('La copia supera el límite de 10 MB.')
    with connect() as db:
        return json.dumps(import_data(db, local_user(db), raw), ensure_ascii=False)


def next_alarm(now=None):
    now = int(time.time()) if now is None else int(now)
    soonest = 0
    with connect() as db:
        for med in db.execute('SELECT * FROM medications WHERE active=1 AND reminders=1').fetchall():
            resolved = {r[0] for r in db.execute('SELECT scheduled_at FROM doses WHERE medication_id=? AND scheduled_at>?', (med['id'], now))}
            # Más de un año cubre incluso pautas diarias omitidas por adelantado.
            for at in occurrences(med, now + 1, now + 366 * 86400, 10000):
                if at not in resolved:
                    soonest = min(soonest, at) if soonest else at
                    break
    return soonest


def tick(alarm_at=0, now=None):
    now = int(time.time()) if now is None else int(now)
    with connect() as db:
        alerts.generate(db, now)
        # Android puede entregar una alarma con retraso en ahorro de batería.
        if alarm_at and now - 3600 <= alarm_at < now - 600:
            for med in db.execute('SELECT * FROM medications WHERE active=1 AND reminders=1').fetchall():
                if alarm_at not in occurrences(med, alarm_at, alarm_at):
                    continue
                dose = db.execute('SELECT status,automatic FROM doses WHERE medication_id=? AND scheduled_at=?', (med['id'], alarm_at)).fetchone()
                if dose and (dose['status'] == 'skipped' or not dose['automatic']):
                    continue
                alerts.add(db, med['user_id'], f"dose:{med['id']}:{alarm_at}", 'Recordatorio de tu pauta',
                           f"{med['name']}: recordatorio pendiente de la hora programada.", 'dose', now)
            db.commit()
        return json.dumps([dict(r) for r in db.execute(
            'SELECT id,title,message,kind FROM alerts WHERE delivered=0 AND read=0 AND created_at>=? ORDER BY id LIMIT 30', (now - 600,))])


def mark_notified(identifiers):
    ids = json.loads(identifiers)
    if not isinstance(ids, list) or any(type(i) is not int for i in ids):
        raise Invalid('Avisos no válidos.')
    with connect() as db:
        db.executemany('UPDATE alerts SET delivered=1 WHERE id=?', [(i,) for i in ids])


def check_sources():
    with connect() as db:
        if not settings(db)['external_sources']:
            return
        medicine_info.enqueue_user(db, local_user(db)['id'])
        db.commit()
    for _ in range(5):
        with connect() as db:
            if not settings(db)['external_sources']:
                break
        if not medicine_info.process_one():
            break
