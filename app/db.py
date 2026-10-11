import os
import sqlite3
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
 instructions TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS doses (
 id INTEGER PRIMARY KEY, medication_id INTEGER NOT NULL REFERENCES medications(id) ON DELETE CASCADE,
 scheduled_at INTEGER NOT NULL, recorded_at INTEGER NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('taken','skipped')), amount INTEGER NOT NULL,
 note TEXT NOT NULL DEFAULT '', UNIQUE(medication_id, scheduled_at)
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
PRAGMA user_version = 1;
"""


class Connection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


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
    with connect(path) as db:
        db.execute("PRAGMA journal_mode=WAL")
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if version > 1:
            raise RuntimeError("La base de datos pertenece a una versión más reciente.")
        db.executescript(SCHEMA)
