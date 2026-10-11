"""Información pública de CIMA/AEMPS; Vademécum se conserva como referencia.

Las consultas automáticas se encolan al iniciar sesión. SQLite conserva los
resultados y los intentos fallidos durante 12 horas, también entre reinicios.
Nunca se consultan las fuentes desde el refresco periódico del dashboard.
"""
import hashlib
import html
import json
import logging
import re
import threading
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from urllib.parse import quote, urlencode, urlsplit

from .db import connect
from .domain import Invalid

TTL = 12 * 3600
BASE = 'https://cima.aemps.es/cima/rest/'
MAX_RESPONSE = 4 * 1024 * 1024
WAKE = threading.Event()
FETCH_LOCK = threading.RLock()
log = logging.getLogger(__name__)
ERROR = 'No se pudo consultar CIMA/AEMPS. Se conserva la información anterior; vuelve a comprobarse cuando transcurran 12 horas desde el intento.'


class SourceUnavailable(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_json(endpoint):
    # Solo rutas construidas por la aplicación. Las URL pegadas nunca se solicitan.
    if endpoint.startswith(('/', 'http')) or '..' in endpoint:
        raise ValueError('Ruta de fuente no válida')
    request = urllib.request.Request(BASE + endpoint, headers={
        'Accept': 'application/json', 'User-Agent': 'Pastillas/0.2 (+https://github.com/kadyto/pastillas)'})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=8) as response:
            if response.status == 204:
                return []
            raw = response.read(MAX_RESPONSE + 1)
            if len(raw) > MAX_RESPONSE:
                raise SourceUnavailable(ERROR)
            return json.loads(raw)
    except (OSError, ValueError) as error:
        raise SourceUnavailable(ERROR) from error


def registry(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9/.-]{0,39}', value) or '..' in value:
        raise Invalid('Número de registro CIMA no válido.')
    return value


def national_code(value):
    if not isinstance(value, str) or (value and not re.fullmatch(r'\d{6}', value)):
        raise Invalid('El código nacional debe tener 6 cifras.')
    return value


def vademecum_url(value):
    if not value:
        return ''
    if not isinstance(value, str) or len(value) > 600:
        raise Invalid('URL de Vademécum no válida.')
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        raise Invalid('URL de Vademécum no válida.') from None
    if (parsed.scheme != 'https' or parsed.netloc.lower() not in ('www.vademecum.es', 'vademecum.es')
            or parsed.query or parsed.fragment or not re.fullmatch(r'/espana/medicamento/\d{1,12}/[a-z0-9-]+/?', parsed.path)):
        raise Invalid('Pega una URL https://www.vademecum.es/espana/medicamento/… de España.')
    return 'https://www.vademecum.es' + parsed.path.rstrip('/')


def equivalents_url(value):
    return vademecum_url(value).replace('/espana/medicamento/', '/espana/equivalencias/') if value else ''


def safe_link(value):
    if not isinstance(value, str) or len(value) > 2000:
        return ''
    try:
        parsed = urlsplit(value)
    except ValueError:
        return ''
    if parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password:
        return value
    return ''


def epoch(value):
    if isinstance(value, (float, int)) and value > 0:
        return int(value / 1000 if value > 100000000000 else value)
    return None


def rows(value):
    if isinstance(value, list) and all(isinstance(item, dict) for item in value):
        return value
    if isinstance(value, dict) and isinstance(value.get('resultados'), list):
        return rows(value['resultados'])
    raise SourceUnavailable(ERROR)


def cached(key, loader, path=None, now=None):
    """Reserva antes de acceder a la red; sin transacción SQLite durante el I/O."""
    now = int(time.time()) if now is None else now
    with FETCH_LOCK:
        with connect(path) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR IGNORE INTO medicine_cache(cache_key) VALUES(?)', (key,))
            entry = db.execute('SELECT * FROM medicine_cache WHERE cache_key=?', (key,)).fetchone()
            if entry['expires_at'] > now:
                if entry['error'] or not entry['checked_at']:
                    raise SourceUnavailable(entry['error'] or 'La consulta sigue en curso. Vuelve a abrir la ficha en unos segundos.')
                return json.loads(entry['data'])
            db.execute('UPDATE medicine_cache SET attempted_at=?,expires_at=?,pending=2,error=? WHERE cache_key=?',
                       (now, now + TTL, 'La comprobación anterior no llegó a completarse.', key))
        try:
            result = loader()
        except Exception as error:
            message = str(error) if isinstance(error, SourceUnavailable) else ERROR
            with connect(path) as db:
                db.execute('UPDATE medicine_cache SET pending=0,error=? WHERE cache_key=?', (message, key))
            raise SourceUnavailable(message) from None
        with connect(path) as db:
            db.execute('UPDATE medicine_cache SET data=?,checked_at=?,pending=0,error=? WHERE cache_key=?',
                       (json.dumps(result, ensure_ascii=False), now, '', key))
        return result


def search(query, page=1, path=None):
    url = ''
    if not isinstance(query, str):
        raise Invalid('Indica el nombre del medicamento o su URL de Vademécum.')
    query = query.strip()
    if query.startswith(('http:', 'https:')):
        url = vademecum_url(query)
        slug = url.rsplit('/', 1)[1].replace('-', ' ')
        query = re.split(r'\s+\d', slug, maxsplit=1)[0].strip()
    if not 2 <= len(query) <= 200:
        raise Invalid('Escribe entre 2 y 200 caracteres para buscar.')
    if type(page) is not int or not 1 <= page <= 10000:
        raise Invalid('Página no válida.')
    key = 'search:' + hashlib.sha256((query.casefold() + ':' + str(page)).encode()).hexdigest()
    result = cached(key, lambda: fetch_json('medicamentos?' + urlencode(dict(nombre=query, pagina=page))), path)
    medicines = rows(result)
    return dict(query=query, vademecum_url=url, source='CIMA / AEMPS', page=page,
                total=result.get('totalFilas', len(medicines)) if isinstance(result, dict) else len(medicines),
                results=[dict(nregistro=registry(str(item['nregistro'])), name=str(item['nombre']),
                              laboratory=str(item.get('labtitular', ''))) for item in medicines])


def catalog(number, path=None):
    number = registry(number)
    def load():
        item = fetch_json('medicamento?' + urlencode(dict(nregistro=number)))
        if not isinstance(item, dict) or str(item.get('nregistro', '')) != number or not item.get('nombre'):
            raise SourceUnavailable(ERROR)
        return item
    return cached('catalog:' + number, load, path)


def catalog_public(number, path=None):
    item = catalog(number, path)
    form = item.get('formaFarmaceuticaSimplificada') or item.get('formaFarmaceutica') or {}
    return dict(nregistro=str(item['nregistro']), name=str(item['nombre']),
                form=form.get('nombre', '') if isinstance(form, dict) else '', strength=str(item.get('dosis', '')),
                presentations=[dict(cn=national_code(str(p['cn'])), name=str(p['nombre']), marketed=bool(p.get('comerc')))
                               for p in rows(item.get('presentaciones', []))])


def link(db, user_id, medication_id, data, path=None):
    from .service import owned
    owned(db, 'medications', medication_id, user_id)
    # Toda la verificación externa ocurre antes del BEGIN IMMEDIATE del llamador.
    number = registry(data.get('nregistro', ''))
    cn = national_code(data.get('cn', ''))
    url = vademecum_url(data.get('vademecum_url', ''))
    item = catalog_public(number, path)
    presentations = item['presentations']
    selected = next((p for p in presentations if p['cn'] == cn), None)
    if presentations and not selected:
        raise Invalid('Selecciona el envase exacto para comprobar sus problemas de suministro.')
    if cn and not selected:
        raise Invalid('El código nacional no pertenece al medicamento seleccionado.')
    db.execute('BEGIN IMMEDIATE')
    owned(db, 'medications', medication_id, user_id)
    db.execute('INSERT INTO medicine_links VALUES(?,?,?,?,?,?) ON CONFLICT(medication_id) DO UPDATE SET '
               'vademecum_url=excluded.vademecum_url,nregistro=excluded.nregistro,cn=excluded.cn,'
               'cima_name=excluded.cima_name,presentation_name=excluded.presentation_name',
               (medication_id, url, number, cn, item['name'], selected['name'] if selected else ''))
    enqueue_user(db, user_id)
    return information(db, medication_id)


def info_key(item):
    return 'info:' + item['nregistro'] + ':' + item['cn']


def enqueue_user(db, user_id, now=None):
    now = int(time.time()) if now is None else now
    items = db.execute('SELECT l.*,m.user_id,m.name FROM medicine_links l JOIN medications m ON m.id=l.medication_id '
                       'WHERE m.user_id=? AND m.active=1 AND (m.end_at IS NULL OR m.end_at>=?)', (user_id, now)).fetchall()
    for item in items:
        key = info_key(item)
        db.execute('INSERT OR IGNORE INTO medicine_cache(cache_key) VALUES(?)', (key,))
        db.execute('UPDATE medicine_cache SET pending=1 WHERE cache_key=? AND expires_at<=?', (key, now))
        entry = db.execute('SELECT * FROM medicine_cache WHERE cache_key=?', (key,)).fetchone()
        if entry['checked_at'] and not entry['error'] and entry['expires_at'] > now:
            publish(db, item, json.loads(entry['data']), now)
    WAKE.set()


def information(db, medication_id, now=None):
    now = int(time.time()) if now is None else now
    item = db.execute('SELECT * FROM medicine_links WHERE medication_id=?', (medication_id,)).fetchone()
    if not item:
        return None
    entry = db.execute('SELECT * FROM medicine_cache WHERE cache_key=?', (info_key(item),)).fetchone()
    payload = json.loads(entry['data']) if entry else {}
    state = 'pending' if entry and entry['pending'] and (entry['pending'] == 1 or entry['attempted_at'] > now - 120) else 'unavailable'
    if entry and not entry['pending'] and entry['checked_at'] and not entry['error']:
        state = 'fresh' if entry['expires_at'] > now else 'stale'
    return dict(link=dict(item), status=state, data=payload, checked_at=entry['checked_at'] if entry else 0,
                attempted_at=entry['attempted_at'] if entry else 0, next_check_at=entry['expires_at'] if entry else 0,
                error=entry['error'] if entry and state != 'pending' else '',
                equivalents_url=equivalents_url(item['vademecum_url']))


def load_information(item):
    # Una comprobación por medicamento/envase: no se reutiliza una ficha caducada.
    medicine = fetch_json('medicamento?' + urlencode(dict(nregistro=item['nregistro'])))
    if not isinstance(medicine, dict) or str(medicine.get('nregistro', '')) != item['nregistro']:
        raise SourceUnavailable(ERROR)
    presentations = rows(medicine.get('presentaciones', []))
    presentation = next((p for p in presentations if str(p.get('cn')) == item['cn']), None)
    if item['cn'] and presentation is None:
        raise SourceUnavailable('El envase vinculado ya no aparece en CIMA. Revisa la vinculación.')
    notes = rows(fetch_json('notas/' + quote(item['nregistro'], safe=''))) if medicine.get('notas') else []
    supply = rows(fetch_json('psuministro/' + item['cn'])) if item['cn'] else []
    notices = []
    for note in notes:
        if note.get('tipo') != 1:
            continue
        url = safe_link(note.get('url'))
        title = str(note.get('asunto') or note.get('ref') or 'Nota de seguridad AEMPS')[:2000]
        notices.append(dict(kind='safety', id='note:' + hashlib.sha256((str(note.get('num', '')) + url + str(note.get('fecha', '')) + title).encode()).hexdigest(),
                            title=title, url=url, date=epoch(note.get('fecha')), message=str(note.get('ref', ''))[:2000]))
    for problem in supply:
        # Nunca atribuir el desabastecimiento de otro tamaño de caja al envase elegido.
        if not problem.get('activo') or str(problem.get('cn')) != item['cn']:
            continue
        notices.append(dict(kind='supply', id='supply:' + item['cn'] + ':' + str(problem.get('fini', '')),
                            title='Problema de suministro: ' + str(problem.get('nombre', item['presentation_name']))[:1000],
                            message=str(problem.get('observ', ''))[:4000], date=epoch(problem.get('fini')),
                            expected_end=epoch(problem.get('ffin')), url='https://cima.aemps.es/cima/publico/detalle.html?nregistro=' + quote(item['nregistro'], safe='')))
    # Si la ficha marca un problema pero el servicio no devuelve detalles, se muestra.
    flagged = bool(presentation.get('psum')) if presentation else bool(medicine.get('psum'))
    if flagged and not any(n['kind'] == 'supply' for n in notices):
        notices.append(dict(kind='supply', id='supply:flag:' + (item['cn'] or item['nregistro']),
                            title='CIMA señala un problema de suministro', date=None,
                            message='Consulta los detalles en CIMA.' if item['cn'] else 'Afecta a alguna presentación; no hay un envase seleccionado.',
                            url='https://cima.aemps.es/cima/publico/detalle.html?nregistro=' + quote(item['nregistro'], safe='')))
    documents = [dict(type=d['tipo'], url=safe_link(d.get('urlHtml') or d.get('url')), pdf_url=safe_link(d.get('url')),
                      segmented=bool(d.get('secc')), date=epoch(d.get('fecha'))) for d in rows(medicine.get('docs', [])) if d.get('tipo') in (1, 2)]
    return dict(name=str(medicine.get('nombre', item['cima_name'])), notices=notices, documents=documents,
                supply_scope='presentation' if item['cn'] else 'medicine', source='CIMA / AEMPS')


def publish(db, item, data, now):
    for notice in data.get('notices', []):
        key = 'medicine:' + str(item['medication_id']) + ':' + hashlib.sha256((item['nregistro'] + ':' + item['cn'] + ':' + notice['id']).encode()).hexdigest()
        inserted = db.execute('INSERT OR IGNORE INTO medicine_notice_seen(medication_id,notice_key) VALUES(?,?)', (item['medication_id'], key))
        if not inserted.rowcount:
            continue
        title = ('Nota de seguridad disponible' if notice['kind'] == 'safety' else 'Problema de suministro') + ' · ' + item['name']
        message = notice['title'] + (' · ' + notice['message'] if notice.get('message') else '')
        if notice.get('date'):
            from datetime import datetime, timezone
            message += ' · Publicado: ' + datetime.fromtimestamp(notice['date'], timezone.utc).strftime('%d/%m/%Y')
        db.execute('INSERT OR IGNORE INTO alerts(user_id,dedupe_key,title,message,kind,created_at) VALUES(?,?,?,?,?,?)',
                   (item['user_id'], key, title, message, notice['kind'], now))


def process_one(path=None, now=None):
    now = int(time.time()) if now is None else now
    with FETCH_LOCK:
        with connect(path) as db:
            db.execute('BEGIN IMMEDIATE')
            entry = db.execute("SELECT * FROM medicine_cache WHERE pending=1 AND cache_key LIKE 'info:%' AND expires_at<=? LIMIT 1", (now,)).fetchone()
            if not entry:
                return False
            items = db.execute('SELECT l.*,m.user_id,m.name FROM medicine_links l JOIN medications m ON m.id=l.medication_id '
                               "WHERE 'info:'||l.nregistro||':'||l.cn=? AND m.active=1 AND (m.end_at IS NULL OR m.end_at>=?)", (entry['cache_key'], now)).fetchall()
            if not items:
                db.execute('UPDATE medicine_cache SET pending=0 WHERE cache_key=?', (entry['cache_key'],))
                return True
            db.execute('UPDATE medicine_cache SET attempted_at=?,expires_at=?,pending=2,error=? WHERE cache_key=?',
                       (now, now + TTL, 'La comprobación anterior no llegó a completarse.', entry['cache_key']))
        try:
            data = load_information(items[0])
        except Exception as error:
            message = str(error) if isinstance(error, SourceUnavailable) else ERROR
            with connect(path) as db:
                db.execute('UPDATE medicine_cache SET pending=0,error=? WHERE cache_key=?', (message, entry['cache_key']))
            log.warning('CIMA/AEMPS no disponible; el siguiente intento respetará la caché de 12 horas.')
            return True
        with connect(path) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('UPDATE medicine_cache SET data=?,checked_at=?,pending=0,error=? WHERE cache_key=?',
                       (json.dumps(data, ensure_ascii=False), now, '', entry['cache_key']))
            # Releer: una vinculación puede cambiar mientras responde el proveedor.
            items = db.execute('SELECT l.*,m.user_id,m.name FROM medicine_links l JOIN medications m ON m.id=l.medication_id '
                               "WHERE 'info:'||l.nregistro||':'||l.cn=? AND m.active=1 AND (m.end_at IS NULL OR m.end_at>=?)", (entry['cache_key'], now)).fetchall()
            for item in items:
                publish(db, item, data, now)
        return True


def worker(stop):
    while not stop.is_set():
        WAKE.clear()
        try:
            while not stop.is_set() and process_one():
                pass
        except Exception:
            log.exception('Error interno al comprobar la información de medicamentos')
        WAKE.wait(30)  # Solo procesa trabajos encolados; no programa nuevas consultas.


class DocumentHTML(HTMLParser):
    ALLOWED = set('p div span h1 h2 h3 h4 h5 h6 ul ol li table thead tbody tfoot tr td th caption strong b em i u sup sub br hr blockquote a'.split())
    BLOCKED = set('script style iframe object embed form button input textarea select svg math template'.split())
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.blocked = []
    def handle_starttag(self, tag, attrs):
        if tag in self.BLOCKED:
            self.blocked.append(tag)
        if self.blocked:
            return
        if tag in self.ALLOWED:
            safe = ''
            values = dict(attrs)
            if tag == 'a' and safe_link(values.get('href')):
                safe = ' href="' + html.escape(values['href'], quote=True) + '" target="_blank" rel="noopener noreferrer"'
            if tag in ('td', 'th'):
                for name in ('colspan', 'rowspan'):
                    if re.fullmatch(r'\d{1,2}', values.get(name, '')):
                        safe += ' ' + name + '="' + values[name] + '"'
            self.parts.append('<' + tag + safe + '>')
        elif tag == 'img':
            self.parts.append('<p>[Imagen: ' + html.escape(dict(attrs).get('alt') or 'consultar el documento original') + ']</p>')
    def handle_endtag(self, tag):
        if self.blocked:
            if tag == self.blocked[-1]:
                self.blocked.pop()
            return
        if tag in self.ALLOWED and tag not in ('br', 'hr'):
            self.parts.append('</' + tag + '>')
    def handle_data(self, value):
        if not self.blocked:
            self.parts.append(html.escape(value))


def sanitize_document(value):
    if not isinstance(value, str):
        raise SourceUnavailable(ERROR)
    parser = DocumentHTML()
    parser.feed(value)
    parser.close()
    return ''.join(parser.parts)


def document(number, kind, path=None):
    number = registry(number)
    if kind not in ('1', '2'):
        raise Invalid('Documento no válido.')
    def load():
        sections = rows(fetch_json('docSegmentado/contenido/' + kind + '?' + urlencode(dict(nregistro=number))))
        if not sections or not any(s.get('contenido') for s in sections):
            raise SourceUnavailable('El documento no está disponible por secciones. Abre el original de AEMPS.')
        return [dict(section=str(s.get('seccion', '')), title=str(s.get('titulo', '')), html=sanitize_document(s.get('contenido', ''))) for s in sections]
    return dict(source='CIMA / AEMPS', sections=cached('doc:' + number + ':' + kind, load, path))
