import os
import sqlite3
import tempfile
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
 password TEXT NOT NULL, admin INTEGER NOT NULL DEFAULT 0,
 timezone TEXT NOT NULL DEFAULT 'Europe/Madrid',
 ntfy_topic TEXT NOT NULL DEFAULT '', ntfy_enabled INTEGER NOT NULL DEFAULT 0,
 stock_alerts INTEGER NOT NULL DEFAULT 1, prescription_alerts INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS sessions (
 token TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 expires INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS prescriptions (
 id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
 title TEXT NOT NULL, doctor TEXT NOT NULL DEFAULT '', reference TEXT NOT NULL DEFAULT '',
 renewal_date TEXT, notes TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS medications (
 id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
 name TEXT NOT NULL, brand TEXT NOT NULL DEFAULT '', form TEXT NOT NULL,
 strength TEXT NOT NULL DEFAULT '', unit TEXT NOT NULL,
 dose INTEGER NOT NULL CHECK(dose > 0), stock INTEGER NOT NULL CHECK(stock >= 0),
 schedule TEXT NOT NULL CHECK(schedule IN ('interval','daily','as_needed')),
 interval_hours REAL NOT NULL DEFAULT 24, times TEXT NOT NULL DEFAULT '[]',
 start_at INTEGER NOT NULL, end_at INTEGER, timezone TEXT NOT NULL,
 active INTEGER NOT NULL DEFAULT 1, reminders INTEGER NOT NULL DEFAULT 1,
 warning_days INTEGER NOT NULL DEFAULT 7,
 prescription_id INTEGER REFERENCES prescriptions(id) ON DELETE SET NULL,
 instructions TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL,
 auto_cursor INTEGER NOT NULL DEFAULT 0, stock_verified_at INTEGER,
 expiry_date TEXT
);
CREATE TABLE IF NOT EXISTS doses (
 id INTEGER PRIMARY KEY, medication_id INTEGER NOT NULL REFERENCES medications(id) ON DELETE CASCADE,
 scheduled_at INTEGER NOT NULL, recorded_at INTEGER NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('taken','skipped')), amount INTEGER NOT NULL,
 note TEXT NOT NULL DEFAULT '', automatic INTEGER NOT NULL DEFAULT 0,
 expected_amount INTEGER NOT NULL DEFAULT 0, UNIQUE(medication_id, scheduled_at)
);
CREATE TABLE IF NOT EXISTS stock_movements (
 id INTEGER PRIMARY KEY, medication_id INTEGER NOT NULL REFERENCES medications(id) ON DELETE CASCADE,
 amount INTEGER NOT NULL, kind TEXT NOT NULL, recorded_at INTEGER NOT NULL,
 note TEXT NOT NULL DEFAULT '', price_cents INTEGER, dose_id INTEGER REFERENCES doses(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS alerts (
 id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
 dedupe_key TEXT NOT NULL, title TEXT NOT NULL, message TEXT NOT NULL,
 kind TEXT NOT NULL, created_at INTEGER NOT NULL, read INTEGER NOT NULL DEFAULT 0,
 delivered INTEGER NOT NULL DEFAULT 0, attempts INTEGER NOT NULL DEFAULT 0,
 last_attempt INTEGER NOT NULL DEFAULT 0,
 UNIQUE(user_id, dedupe_key)
);
CREATE INDEX IF NOT EXISTS med_owner ON medications(user_id);
CREATE INDEX IF NOT EXISTS dose_time ON doses(medication_id, scheduled_at);
CREATE INDEX IF NOT EXISTS alert_owner ON alerts(user_id, created_at);
CREATE TABLE IF NOT EXISTS medicine_links (
 medication_id INTEGER PRIMARY KEY REFERENCES medications(id) ON DELETE CASCADE,
 vademecum_url TEXT NOT NULL DEFAULT '', nregistro TEXT NOT NULL,
 cn TEXT NOT NULL DEFAULT '', cima_name TEXT NOT NULL, presentation_name TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS medicine_cache (
 cache_key TEXT PRIMARY KEY, data TEXT NOT NULL DEFAULT '{}',
 attempted_at INTEGER NOT NULL DEFAULT 0, checked_at INTEGER NOT NULL DEFAULT 0,
 expires_at INTEGER NOT NULL DEFAULT 0, pending INTEGER NOT NULL DEFAULT 0,
 error TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS medicine_notice_seen (
 medication_id INTEGER NOT NULL REFERENCES medications(id) ON DELETE CASCADE,
 notice_key TEXT NOT NULL, PRIMARY KEY(medication_id,notice_key)
);
CREATE TABLE IF NOT EXISTS app_updates (
 id INTEGER PRIMARY KEY CHECK(id=1), latest_version TEXT NOT NULL DEFAULT '',
 latest_commit TEXT NOT NULL DEFAULT '', attempted_at INTEGER NOT NULL DEFAULT 0,
 checked_at INTEGER NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT '',
 deploy_status TEXT NOT NULL DEFAULT '', deploy_requested_at INTEGER NOT NULL DEFAULT 0,
 deploy_target TEXT NOT NULL DEFAULT '', deploy_error TEXT NOT NULL DEFAULT ''
);
INSERT OR IGNORE INTO app_updates(id) VALUES (1);
"""


class Connection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


class StorageError(RuntimeError):
    """El almacenamiento configurado no está disponible para SQLite."""


def storage_message(path, error):
    identity = f"{os.getuid()}:{os.getgid()}" if hasattr(os, "getuid") else "el usuario del proceso"
    return (
        f"No se puede usar la base de datos {path} con UID:GID {identity}: {error}. "
        "La carpeta debe permitir crear y modificar la base y sus archivos SQLite -wal/-shm. "
        "En Dockhand revisa DATA_DIR, APP_UID, APP_GID y los permisos/ACL de la carpeta del NAS, "
        "o usa compose.dockhand.volume.yaml para una instalación con un volumen Docker nuevo."
    )


def prepare_storage(path):
    if str(path) == ":memory:":
        return
    target = Path(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        # SQLite WAL también necesita escribir en la carpeta, aunque la base ya exista.
        with tempfile.TemporaryFile(prefix=".pastillas-storage-", dir=target.parent) as probe:
            probe.write(b"pastillas")
            probe.flush()
            os.fsync(probe.fileno())
        if target.exists():
            if not target.is_file():
                raise OSError("DATABASE_PATH debe señalar a un archivo, no a una carpeta")
            descriptor = os.open(target, os.O_RDWR)
            os.close(descriptor)
    except OSError as error:
        raise StorageError(storage_message(path, error.strerror or str(error))) from error


def connect(path=None):
    path = path or os.environ.get("DATABASE_PATH", "data/pastillas.sqlite")
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=15, factory=Connection)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=15000")
    return db


def initialize(path=None):
    path = path or os.environ.get("DATABASE_PATH", "data/pastillas.sqlite")
    prepare_storage(path)
    try:
        with connect(path) as db:
            db.execute("PRAGMA journal_mode=WAL")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > 5:
                raise RuntimeError("La base de datos pertenece a una versión más reciente.")
            if version == 1 and str(path) != ':memory:':
                # Copia consistente incluso con WAL, antes de la primera migración.
                backup_path = str(path) + '.pre-v2.sqlite'
                if not Path(backup_path).exists():
                    with sqlite3.connect(backup_path) as backup:
                        db.backup(backup)
                    os.chmod(backup_path, 0o600)
            if version in (1,2) and str(path) != ':memory:':
                backup_path = str(path) + '.pre-v3.sqlite'
                if not Path(backup_path).exists():
                    backup = sqlite3.connect(backup_path)
                    try:
                        db.backup(backup)
                    finally:
                        backup.close()
                    os.chmod(backup_path,0o600)
            if version in (1,2,3) and str(path) != ':memory:':
                backup_path = str(path) + '.pre-v4.sqlite'
                if not Path(backup_path).exists():
                    backup = sqlite3.connect(backup_path)
                    try:
                        db.backup(backup)
                    finally:
                        backup.close()
                    os.chmod(backup_path,0o600)
            if version in (1,2,3,4) and str(path) != ':memory:':
                backup_path = str(path) + '.pre-v5.sqlite'
                if not Path(backup_path).exists():
                    backup = sqlite3.connect(backup_path)
                    try:
                        db.backup(backup)
                    finally:
                        backup.close()
                    os.chmod(backup_path,0o600)
            db.executescript(SCHEMA)
            # ALTER conserva las tablas existentes, sus claves y todos los movimientos.
            db.execute('BEGIN IMMEDIATE')
            if version in (1,2):
                columns = {r[1] for r in db.execute('PRAGMA table_info(medications)')}
                if 'auto_cursor' not in columns:
                    db.execute('ALTER TABLE medications ADD COLUMN auto_cursor INTEGER NOT NULL DEFAULT 0')
                if 'stock_verified_at' not in columns:
                    db.execute('ALTER TABLE medications ADD COLUMN stock_verified_at INTEGER')
                db.execute('UPDATE medications SET auto_cursor=?',(int(time.time()),))
                columns = {r[1] for r in db.execute('PRAGMA table_info(doses)')}
                if 'automatic' not in columns:
                    db.execute('ALTER TABLE doses ADD COLUMN automatic INTEGER NOT NULL DEFAULT 0')
                if 'expected_amount' not in columns:
                    db.execute('ALTER TABLE doses ADD COLUMN expected_amount INTEGER NOT NULL DEFAULT 0')
                    db.execute('UPDATE doses SET expected_amount=amount')
            columns = {r[1] for r in db.execute('PRAGMA table_info(medications)')}
            if 'expiry_date' not in columns:
                db.execute('ALTER TABLE medications ADD COLUMN expiry_date TEXT')
            db.execute('PRAGMA user_version=5')
    except sqlite3.OperationalError as error:
        raise StorageError(storage_message(path, str(error))) from error
