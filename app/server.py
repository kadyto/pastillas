"""Servidor HTTP sin dependencias externas, con SQLite persistente."""
import hashlib
import json
import logging
import mimetypes
import os
import re
import secrets
import signal
import sqlite3
import threading
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import __version__
from . import alerts, auth, service
from .db import StorageError, connect, initialize
from .domain import Invalid

STATIC = Path(__file__).parent / "static"
log = logging.getLogger(__name__)
FAILED_LOGINS = {}
LOGIN_LOCK = threading.Lock()
MAX_BODY = 64 * 1024


class Unauthorized(Exception):
    pass


class Forbidden(Exception):
    pass


class Handler(BaseHTTPRequestHandler):
    server_version = "Pastillas"

    def log_message(self, fmt, *args):
        # Sin direcciones, rutas con parámetros ni datos médicos en el registro.
        pass

    def send(self, status, body, content_type="application/json; charset=utf-8", headers=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False, allow_nan=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; worker-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def cookie(self, token=""):
        value = f"pastillas_session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={604800 if token else 0}"
        if os.environ.get("COOKIE_SECURE", "false").lower() == "true":
            value += "; Secure"
        return {"Set-Cookie": value}

    def user(self, db):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
        except Exception:
            pass
        token = cookie.get("pastillas_session")
        result = auth.current_user(db, token.value if token else "")
        if not result:
            raise Unauthorized("Inicia sesión para continuar.")
        return result

    def body(self):
        if self.headers.get("Content-Type", "").split(";")[0].lower() != "application/json":
            raise Invalid("Envía el formulario como JSON.")
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise Invalid("Tamaño de petición no válido.") from None
        if length < 0 or length > MAX_BODY:
            raise Invalid("La petición es demasiado grande.")
        # Sin dominio canónico: cada acceso usa su propia URL, también detrás de un proxy.
        # JSON, SameSite y Fetch Metadata protegen las operaciones sin listas de dominios.
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            raise Forbidden("Petición de otro sitio bloqueada.")
        try:
            data = json.loads(self.rfile.read(length), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        except (ValueError, UnicodeDecodeError):
            raise Invalid("El formulario no contiene JSON válido.") from None
        if not isinstance(data, dict):
            raise Invalid("Formulario no válido.")
        return data

    def handle_request(self):
        try:
            parsed = urlsplit(self.path)
            path = parsed.path
            if path == "/healthz":
                with connect() as db:
                    db.execute("SELECT 1").fetchone()
                return self.send(200, dict(status="ok", version=__version__))
            if not path.startswith("/api/"):
                if self.command not in ("GET", "HEAD"):
                    return self.send(405, dict(error="Método no permitido."))
                filename = "index.html" if path == "/" else path.lstrip("/")
                target = (STATIC / filename).resolve()
                if STATIC.resolve() not in target.parents or not target.is_file():
                    return self.send(404, dict(error="Página no encontrada."))
                return self.send(200, target.read_bytes(), mimetypes.guess_type(target)[0] or "application/octet-stream")
            with connect() as db:
                self.api(db, path, parse_qs(parsed.query))
        except Unauthorized as error:
            self.send(401, dict(error=str(error)))
        except Forbidden as error:
            self.send(403, dict(error=str(error)))
        except service.NotFound as error:
            self.send(404, dict(error=str(error)))
        except (service.Conflict, sqlite3.IntegrityError) as error:
            self.send(409, dict(error=str(error) if isinstance(error, service.Conflict) else "El registro ya existe o está relacionado con otros datos."))
        except Invalid as error:
            self.send(400, dict(error=str(error)))
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            log.exception("Error al procesar una petición")
            self.send(500, dict(error="No se ha podido completar la operación. Consulta los registros del servidor."))

    def api(self, db, path, query):
        method = self.command
        now = int(time.time())
        if path == "/api/session" and method == "GET":
            try:
                user = auth.public_user(self.user(db))
            except Unauthorized:
                user = None
            return self.send(200, dict(user=user, setup_required=not bool(db.execute("SELECT 1 FROM users LIMIT 1").fetchone()), version=__version__, ntfy_base_url=alerts.ntfy_base()))
        data = self.body() if method in ("POST", "PUT", "DELETE") else {}
        if path in ("/api/login", "/api/setup") and method == "POST":
            ip = self.client_address[0]
            with LOGIN_LOCK:
                expired = [key for key, (_, started) in FAILED_LOGINS.items() if now - started >= 900]
                for key in expired:
                    del FAILED_LOGINS[key]
                attempts, started = FAILED_LOGINS.get(ip, (0, now))
                if attempts >= 10:
                    return self.send(429, dict(error="Demasiados intentos. Espera 15 minutos."))
                # Se reserva el intento antes del hash; también limita peticiones concurrentes.
                FAILED_LOGINS[ip] = (attempts + 1, started)
            username, password = auth.credentials(data)
            db.execute("BEGIN IMMEDIATE")
            if path == "/api/setup":
                if db.execute("SELECT 1 FROM users LIMIT 1").fetchone():
                    raise service.Conflict("La aplicación ya está configurada. Inicia sesión.")
                ident = service.create_user(db, data)
                db.execute("UPDATE users SET admin=1 WHERE id=?", (ident,))
                user = db.execute("SELECT * FROM users WHERE id=?", (ident,)).fetchone()
            else:
                user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
                if not user:
                    # Igual coste para usuarios inexistentes y contraseñas incorrectas.
                    auth.hash_password(password)
                if not user or not auth.verify_password(password, user["password"]):
                    raise Unauthorized("Usuario o contraseña incorrectos.")
            token = auth.session(db, user["id"])
            db.commit()
            with LOGIN_LOCK:
                FAILED_LOGINS.pop(ip, None)
            return self.send(200, auth.public_user(user), headers=self.cookie(token))
        user = self.user(db)
        if method in ("POST", "PUT", "DELETE"):
            db.execute("BEGIN IMMEDIATE")
        elif method == "GET":
            db.execute("BEGIN")
        if path == "/api/logout" and method == "POST":
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
            token = cookie.get("pastillas_session")
            if token:
                db.execute("DELETE FROM sessions WHERE token=?", (hashlib.sha256(token.value.encode()).hexdigest(),))
            db.commit()
            return self.send(200, dict(ok=True), headers=self.cookie())
        if path == "/api/dashboard" and method == "GET":
            return self.send(200, service.dashboard(db, user, now))
        if path == "/api/agenda" and method == "GET":
            day = query.get("day", [""])[0]
            if not day:
                raise Invalid("Selecciona una fecha.")
            return self.send(200, service.agenda(db, user, day, now))
        if path == "/api/medications" and method == "POST":
            ident = service.medication_save(db, user, data)
            db.commit()
            return self.send(201, dict(id=ident))
        match = re.fullmatch(r"/api/medications/(\d+)(?:/(stock|doses|history))?", path)
        if match:
            ident, action = int(match[1]), match[2]
            if action == "history" and method == "GET":
                return self.send(200, service.history(db, user["id"], ident))
            if action == "stock" and method == "POST":
                result = service.stock_add(db, user["id"], ident, data)
            elif action == "doses" and method == "POST":
                result = service.record_dose(db, user["id"], ident, data)
            elif not action and method == "PUT":
                result = service.medication_save(db, user, data, ident)
            elif not action and method == "DELETE":
                service.owned(db, "medications", ident, user["id"])
                db.execute("DELETE FROM medications WHERE id=?", (ident,))
                result = ident
            else:
                return self.send(405, dict(error="Método no permitido."))
            db.commit()
            return self.send(200, dict(id=result))
        match = re.fullmatch(r"/api/doses/(\d+)", path)
        if match and method == "DELETE":
            service.undo_dose(db, user["id"], int(match[1]))
            db.commit()
            return self.send(200, dict(ok=True))
        match = re.fullmatch(r"/api/prescriptions(?:/(\d+))?", path)
        if match and method in ("POST", "PUT", "DELETE"):
            ident = int(match[1]) if match[1] else None
            if ident:
                service.owned(db, "prescriptions", ident, user["id"])
            if method == "POST" and ident is None:
                ident = service.insert(db, "prescriptions", dict(service.prescription_input(data), user_id=user["id"]))
            elif method == "PUT" and ident:
                service.update(db, "prescriptions", ident, service.prescription_input(data))
            elif method == "DELETE" and ident:
                db.execute("DELETE FROM prescriptions WHERE id=?", (ident,))
            else:
                return self.send(405, dict(error="Método no permitido."))
            db.commit()
            return self.send(200, dict(id=ident))
        if path == "/api/settings" and method == "PUT":
            result = service.settings_save(db, user, data)
            db.commit()
            return self.send(200, result)
        if path == "/api/password" and method == "PUT":
            old = data.get("current_password", "")
            if not isinstance(old, str) or len(old) > 256 or not auth.verify_password(old, user["password"]):
                raise Invalid("La contraseña actual no es correcta.")
            _, password = auth.credentials(dict(username=user["username"], password=data.get("password")))
            db.execute("UPDATE users SET password=? WHERE id=?", (auth.hash_password(password), user["id"]))
            db.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
            token = auth.session(db, user["id"])
            db.commit()
            return self.send(200, dict(ok=True), headers=self.cookie(token))
        if path == "/api/users" and method == "POST":
            if not user["admin"]:
                raise Forbidden("Solo la cuenta administradora puede crear usuarios.")
            result = service.create_user(db, data)
            db.commit()
            return self.send(201, dict(id=result))
        if path == "/api/alerts" and method == "GET":
            return self.send(200, [dict(r) for r in db.execute("SELECT * FROM alerts WHERE user_id=? ORDER BY id DESC LIMIT 100", (user["id"],))])
        if path == "/api/alerts/read" and method == "POST":
            db.execute("UPDATE alerts SET read=1 WHERE user_id=?", (user["id"],))
            db.commit()
            return self.send(200, dict(ok=True))
        if path == "/api/export" and method == "GET":
            return self.send(200, service.export_data(db, user), headers={"Content-Disposition": 'attachment; filename="pastillas-export.json"'})
        return self.send(404, dict(error="Ruta no encontrada."))

    do_GET = handle_request
    do_HEAD = handle_request
    do_POST = handle_request
    do_PUT = handle_request
    do_DELETE = handle_request


class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 64

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(15)
        return connection, address


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    os.umask(0o077)
    alerts.ntfy_base()
    try:
        initialize()
    except StorageError as error:
        log.error("%s", error)
        raise SystemExit(1) from None
    with connect() as db:
        auth.initial_user(db)
    stop = threading.Event()
    thread = threading.Thread(target=alerts.worker, args=(stop,), daemon=True)
    thread.start()
    server = Server((os.environ.get("HOST", "0.0.0.0"), int(os.environ.get("PORT", "8000"))), Handler)
    def shutdown(signum, frame):
        stop.set()
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    log.info("Pastillas %s listo en el puerto %s", __version__, server.server_port)
    try:
        server.serve_forever()
    finally:
        stop.set()
        server.server_close()
        thread.join(timeout=7)


if __name__ == "__main__":
    main()
