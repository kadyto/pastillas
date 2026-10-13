"""Comprobación diaria de GitHub y despliegue opcional mediante Dockhand."""
import hashlib
import hmac
import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from . import __version__
from .db import connect
from .domain import Invalid

DAY = 86400
REPOSITORY = 'https://github.com/kadyto/pastillas'
REF_URL = 'https://api.github.com/repos/kadyto/pastillas/git/ref/heads/main'
CHECK_LOCK = threading.Lock()
DEPLOY_LOCK = threading.Lock()
log = logging.getLogger(__name__)


def version(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{1,6}\.\d{1,6}\.\d{1,6}', value):
        raise ValueError('Versión no válida')
    return tuple(map(int, value.split('.')))


def webhook_settings():
    url = os.environ.get('DOCKHAND_WEBHOOK_URL', '').strip()
    secret = os.environ.get('DOCKHAND_WEBHOOK_SECRET', '')
    if not url and not secret:
        return None
    try:
        parsed = urlsplit(url)
        parsed.port
        valid = (parsed.scheme in ('http', 'https') and parsed.hostname and not parsed.username
                 and not parsed.password and not parsed.query and not parsed.fragment
                 and re.fullmatch(r'/api/git/(?:stacks/[1-9]\d*/webhook|webhook/[1-9]\d*)', parsed.path))
    except ValueError:
        valid = False
    if not valid or not secret:
        raise Invalid('Configura la URL del webhook de Dockhand y su secreto en el stack.')
    return url, secret


def status(db, now=None):
    now = int(time.time()) if now is None else now
    row = dict(db.execute('SELECT * FROM app_updates WHERE id=1').fetchone())
    latest = row['latest_version']
    comparison = version(__version__) < version(latest) if latest else False
    if row['error']:
        state = 'unavailable'
    elif not row['checked_at']:
        state = 'unchecked'
    elif comparison:
        state = 'available'
    elif version(__version__) > version(latest):
        state = 'ahead'
    else:
        state = 'current'
    config_error = ''
    try:
        configured = bool(webhook_settings())
    except Invalid as error:
        configured = False
        config_error = str(error)
    return dict(installed_version=__version__, latest_version=latest or None,
                state=state, update_available=comparison, checking=CHECK_LOCK.locked(),
                checked_at=row['checked_at'] or None, attempted_at=row['attempted_at'] or None,
                next_check_at=row['attempted_at'] + DAY if row['attempted_at'] else now,
                error=row['error'], repository_url=REPOSITORY,
                archive_url=REPOSITORY + '/archive/refs/heads/main.tar.gz',
                deployment_configured=configured, deployment_configuration_error=config_error,
                deploy_status=row['deploy_status'], deploy_target=row['deploy_target'],
                deploy_requested_at=row['deploy_requested_at'] or None, deploy_error=row['deploy_error'])


def read_response(response, limit=65536):
    if response.status != 200:
        raise ValueError('Respuesta no válida')
    body = response.read(limit + 1)
    if len(body) > limit:
        raise ValueError('Respuesta demasiado grande')
    return body.decode('utf-8')


def check(force=False, now=None, path=None, opener=None):
    now = int(time.time()) if now is None else now
    if not CHECK_LOCK.acquire(blocking=False):
        with connect(path) as db:
            return status(db, now)
    try:
        with connect(path) as db:
            cached = status(db, now)
            if not force and cached['attempted_at'] and now < cached['next_check_at']:
                cached['checking'] = False
                return cached
            db.execute('UPDATE app_updates SET attempted_at=? WHERE id=1', (now,))
        open_request = opener or urllib.request.urlopen
        headers = {'User-Agent': f'Pastillas/{__version__}', 'Accept': 'application/json'}
        try:
            with open_request(urllib.request.Request(REF_URL, headers=headers), timeout=5) as response:
                sha = json.loads(read_response(response))['object']['sha']
            if not isinstance(sha, str) or not re.fullmatch(r'[a-f0-9]{40}', sha):
                raise ValueError('Commit no válido')
            url = f'https://raw.githubusercontent.com/kadyto/pastillas/{sha}/app/__init__.py'
            with open_request(urllib.request.Request(url, headers=headers), timeout=5) as response:
                source = read_response(response)
            match = re.search(r'^__version__\s*=\s*[\'"]([0-9.]+)[\'"]\s*$', source, re.MULTILINE)
            if not match:
                raise ValueError('No se ha encontrado la versión')
            latest = match.group(1)
            version(latest)
            with connect(path) as db:
                db.execute('UPDATE app_updates SET latest_version=?,latest_commit=?,checked_at=?,error=\'\' WHERE id=1',
                           (latest, sha, now))
        except Exception:
            # Solo se guarda un mensaje fijo, sin URLs privadas ni credenciales.
            with connect(path) as db:
                db.execute('UPDATE app_updates SET error=? WHERE id=1',
                           ('No se pudo comprobar la versión en GitHub. Vuelve a intentarlo.',))
            log.warning('No se pudo comprobar GitHub; el siguiente intento automático será dentro de 24 horas.')
    finally:
        CHECK_LOCK.release()
    with connect(path) as db:
        return status(db, now)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def deploy(target, sha, settings, path=None, opener=None):
    url, secret = settings
    payload = json.dumps({'ref': 'refs/heads/main', 'after': sha,
                          'repository': {'full_name': 'kadyto/pastillas'},
                          'pastillas_version': target}, separators=(',', ':')).encode()
    signature = 'sha256=' + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    request = urllib.request.Request(url, data=payload, headers={
        'Content-Type': 'application/json', 'User-Agent': f'Pastillas/{__version__}',
        'X-Hub-Signature-256': signature, 'X-GitHub-Event': 'push'})
    with connect(path) as db:
        db.execute("UPDATE app_updates SET deploy_status='running' WHERE id=1")
    outcome, error = 'requested', ''
    try:
        open_request = opener or urllib.request.build_opener(NoRedirect()).open
        with open_request(request, timeout=90) as response:
            result = json.loads(read_response(response))
        if result.get('success') is not True:
            outcome, error = 'failed', 'Dockhand no pudo desplegar la actualización. Revisa su registro del stack.'
        elif result.get('skipped'):
            outcome, error = 'skipped', 'Dockhand no detectó cambios. Revisa el repositorio, la rama y las opciones de construcción del stack.'
    except urllib.error.HTTPError as response:
        outcome = 'failed'
        error = ('Dockhand rechazó la solicitud. Revisa la URL y el secreto del webhook.'
                 if response.code in (401, 403, 404) else 'Dockhand devolvió un error. Revisa el registro del stack.')
    except Exception:
        # El servidor puede reiniciarse antes de devolver la respuesta: no se repite el webhook.
        outcome, error = 'unknown', 'No se recibió el resultado de Dockhand. Comprueba el despliegue antes de repetir la actualización.'
    with connect(path) as db:
        db.execute('UPDATE app_updates SET deploy_status=?,deploy_error=? WHERE id=1', (outcome, error))


def request_deploy(now=None, path=None, launch=None):
    now = int(time.time()) if now is None else now
    settings = webhook_settings()
    if not settings:
        raise Invalid('Configura primero el webhook de Dockhand en el stack. Consulta las instrucciones de actualización.')
    if not DEPLOY_LOCK.acquire(blocking=False):
        raise Invalid('Ya hay una actualización en preparación.')
    try:
        with connect(path) as db:
            current = status(db, now)
        if current['deploy_status'] in ('queued', 'running'):
            raise Invalid('Ya hay una actualización en curso. Comprueba el despliegue en Dockhand.')
        if current['error'] or not current['checked_at'] or now - current['checked_at'] >= DAY:
            current = check(force=True, now=now, path=path)
        if current['error'] or current['checking'] or not current['checked_at']:
            raise Invalid('Comprueba la versión en GitHub antes de actualizar.')
        if not current['update_available']:
            raise Invalid('Ya tienes la última versión publicada en GitHub.')
        with connect(path) as db:
            row = db.execute('SELECT latest_commit FROM app_updates WHERE id=1').fetchone()
            sha = row['latest_commit']
            target = current['latest_version']
            db.execute("UPDATE app_updates SET deploy_status='queued',deploy_requested_at=?,deploy_target=?,deploy_error='' WHERE id=1",
                       (now, target))
        task = lambda: deploy(target, sha, settings, path=path)
        if launch:
            launch(task)
        else:
            threading.Thread(target=task, daemon=True).start()
    finally:
        DEPLOY_LOCK.release()
    with connect(path) as db:
        return status(db, now)


def recover(path=None):
    """Resuelve un despliegue interrumpido al arrancar el contenedor nuevo."""
    with connect(path) as db:
        current = status(db)
        target = current['deploy_target']
        if target and version(__version__) >= version(target):
            db.execute("UPDATE app_updates SET deploy_status='completed',deploy_error='' WHERE id=1")
        elif current['deploy_status'] in ('queued', 'running'):
            db.execute("UPDATE app_updates SET deploy_status='unknown',deploy_error=? WHERE id=1",
                       ('El despliegue quedó sin confirmar. Comprueba su estado en Dockhand.',))


def worker(stop):
    while not stop.is_set():
        try:
            check()
        except Exception:
            log.exception('Error en el comprobador de versiones')
        stop.wait(60)
