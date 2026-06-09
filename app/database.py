"""PatchPilot - Database layer (SQLite, parameterized queries only)."""
import os
import sqlite3
from contextlib import contextmanager

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.environ.get("PATCHPILOT_DATA", os.path.join(BASE_DIR, "data"))
DB_PATH = os.path.join(DATA_DIR, "patchpilot.db")
KEYS_DIR = os.path.join(DATA_DIR, "keys")
SSH_KEY_PATH = os.path.join(KEYS_DIR, "id_ed25519")

# Point HOME at our data directory. The systemd unit runs with
# ProtectHome=true, which makes the service user's real home (under /home or
# /root) inaccessible. asyncssh expands "~/.ssh" for default lookups, so
# without this it tries to read /home/<user>/.ssh and fails with
# "Permission denied". Our data dir lives under /opt and is always accessible.
os.environ["HOME"] = DATA_DIR

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    username          TEXT NOT NULL UNIQUE,
    password_hash     TEXT NOT NULL DEFAULT '',
    totp_secret       TEXT NOT NULL DEFAULT '',
    totp_enabled      INTEGER NOT NULL DEFAULT 0,
    is_admin          INTEGER NOT NULL DEFAULT 0,
    pending           INTEGER NOT NULL DEFAULT 0,
    activation_hash   TEXT NOT NULL DEFAULT '',
    activation_expires REAL,
    created_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS recovery_codes (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    code_hash TEXT NOT NULL,
    used      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS machines (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    host            TEXT NOT NULL,
    port            INTEGER NOT NULL DEFAULT 22,
    username        TEXT NOT NULL DEFAULT 'root',
    os_info         TEXT,
    os_type         TEXT,
    reboot_required INTEGER,
    last_action     TEXT,
    last_status     TEXT,
    last_run        TEXT,
    pending_updates INTEGER,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(host, port, username)
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash  TEXT PRIMARY KEY,
    csrf_token  TEXT NOT NULL DEFAULT '',
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    mfa_pending INTEGER NOT NULL DEFAULT 0,
    expires_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS schedule (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    enabled       INTEGER NOT NULL DEFAULT 0,
    freq          TEXT NOT NULL DEFAULT 'daily',   -- 'daily' or 'weekly'
    hour          INTEGER NOT NULL DEFAULT 3,
    minute        INTEGER NOT NULL DEFAULT 0,
    weekday       INTEGER NOT NULL DEFAULT 0,      -- 0=Monday .. 6=Sunday (weekly)
    last_run_date TEXT NOT NULL DEFAULT ''
);
INSERT OR IGNORE INTO schedule (id) VALUES (1);
"""


def _migrate(db):
    """Apply small schema migrations for databases created by older versions."""
    sess_cols = {r["name"] for r in db.execute("PRAGMA table_info(sessions)").fetchall()}
    if "csrf_token" not in sess_cols:
        # Old sessions lack a CSRF token; drop them so everyone re-logs in cleanly.
        db.execute("DROP TABLE sessions")
        db.executescript(SCHEMA)

    # users: add multi-user / activation columns on older databases
    user_cols = {r["name"] for r in db.execute("PRAGMA table_info(users)").fetchall()}
    added = []
    for col, ddl in (
        ("is_admin", "is_admin INTEGER NOT NULL DEFAULT 0"),
        ("pending", "pending INTEGER NOT NULL DEFAULT 0"),
        ("activation_hash", "activation_hash TEXT NOT NULL DEFAULT ''"),
        ("activation_expires", "activation_expires REAL"),
    ):
        if col not in user_cols:
            db.execute(f"ALTER TABLE users ADD COLUMN {ddl}")
            added.append(col)
    if "is_admin" in added:
        # Promote the original installer-created account (lowest id) to admin.
        row = db.execute("SELECT MIN(id) AS mid FROM users").fetchone()
        if row and row["mid"] is not None:
            db.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (row["mid"],))

    # machines: add pending_updates column on older databases
    machine_cols = {r["name"] for r in db.execute("PRAGMA table_info(machines)").fetchall()}
    for col in ("pending_updates INTEGER", "os_type TEXT", "reboot_required INTEGER"):
        if col.split()[0] not in machine_cols:
            db.execute(f"ALTER TABLE machines ADD COLUMN {col}")


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
