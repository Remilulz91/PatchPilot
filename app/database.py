"""PatchPilot - Database layer (SQLite, parameterized queries only)."""
import os
import sqlite3
from contextlib import contextmanager

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get("PATCHPILOT_DATA", os.path.join(BASE_DIR, "data"))
DB_PATH = os.path.join(DATA_DIR, "patchpilot.db")
KEYS_DIR = os.path.join(DATA_DIR, "keys")
SSH_KEY_PATH = os.path.join(KEYS_DIR, "id_ed25519")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    totp_secret   TEXT NOT NULL,
    totp_enabled  INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS machines (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    host        TEXT NOT NULL,
    port        INTEGER NOT NULL DEFAULT 22,
    username    TEXT NOT NULL DEFAULT 'root',
    os_info     TEXT,
    last_action TEXT,
    last_status TEXT,
    last_run    TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(host, port, username)
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash  TEXT PRIMARY KEY,
    csrf_token  TEXT NOT NULL DEFAULT '',
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    mfa_pending INTEGER NOT NULL DEFAULT 0,
    expires_at  REAL NOT NULL
);
"""


def _migrate(db):
    """Apply small schema migrations for databases created by older versions."""
    cols = {r["name"] for r in db.execute("PRAGMA table_info(sessions)").fetchall()}
    if "csrf_token" not in cols:
        # Old sessions lack a CSRF token; drop them so everyone re-logs in cleanly.
        db.execute("DROP TABLE sessions")
        db.executescript(SCHEMA)


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(KEYS_DIR, exist_ok=True)
    with get_db() as db:
        db.executescript(SCHEMA)
        _migrate(db)
