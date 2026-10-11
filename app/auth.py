import hashlib
import hmac
import os
import re
import secrets
import time

from .domain import Invalid


def credentials(data):
    username = data.get("username", "")
    password = data.get("password", "")
    if not isinstance(username, str) or not re.fullmatch(r"[\w.@-]{3,60}", username, re.UNICODE):
        raise Invalid("El usuario debe tener de 3 a 60 letras, números o . @ _ -.")
    if not isinstance(password, str) or not 12 <= len(password) <= 256:
        raise Invalid("La contraseña debe tener de 12 a 256 caracteres.")
    return username, password


def hash_password(password):
    salt = secrets.token_hex(16)
    hashed = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
    return salt + ":" + hashed.hex()


def verify_password(password, encoded):
    salt, expected = encoded.split(":")
    hashed = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
    return hmac.compare_digest(hashed.hex(), expected)


def session(db, user_id):
    token = secrets.token_urlsafe(32)
    db.execute("DELETE FROM sessions WHERE expires < ?", (int(time.time()),))
    db.execute("INSERT INTO sessions(token,user_id,expires) VALUES (?,?,?)",
               (hashlib.sha256(token.encode()).hexdigest(), user_id, int(time.time()) + 86400 * 7))
    return token


def current_user(db, token):
    if not token:
        return None
    return db.execute("SELECT u.* FROM users u JOIN sessions s ON u.id=s.user_id WHERE s.token=? AND s.expires>?",
                      (hashlib.sha256(token.encode()).hexdigest(), int(time.time()))).fetchone()


def session_tokens(cookie_headers):
    """Lee solo nuestra cookie: valores ajenos no deben invalidar una sesión."""
    result = []
    for header in cookie_headers:
        for fragment in header.split(";"):
            name, separator, value = fragment.strip().partition("=")
            if separator and name == "pastillas_session":
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] == '"':
                    value = value[1:-1]
                # Los tokens se generan con token_urlsafe(32), sin interpretar datos de otras apps.
                if re.fullmatch(r"[A-Za-z0-9_-]{43}", value) and value not in result:
                    result.append(value)
    return result


def public_user(row):
    return {k: row[k] for k in ("id", "username", "admin", "timezone", "ntfy_topic", "ntfy_enabled", "stock_alerts", "prescription_alerts")}


def initial_user(db):
    username = os.environ.get("INITIAL_ADMIN_USER", "")
    password = os.environ.get("INITIAL_ADMIN_PASSWORD", "")
    if username or password:
        username, password = credentials(dict(username=username, password=password))
        db.execute("BEGIN IMMEDIATE")
        if not db.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            db.execute("INSERT INTO users(username,password,admin,ntfy_topic) VALUES (?,?,1,?)",
                       (username, hash_password(password), "pastillas-" + secrets.token_hex(12)))
        db.commit()
