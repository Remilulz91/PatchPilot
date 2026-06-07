"""PatchPilot - Authentification : bcrypt + sessions serveur + MFA TOTP."""
import hashlib
import secrets
import time

import bcrypt
import pyotp

from .database import get_db

SESSION_LIFETIME = 12 * 3600  # 12 heures
COOKIE_NAME = "pp_session"

# Anti brute-force : 5 échecs => blocage 15 min (par IP)
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 900
_failed: dict[str, list[float]] = {}


# ---------- Mots de passe ----------

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


# ---------- Anti brute-force ----------

def is_locked(ip: str) -> bool:
    now = time.time()
    attempts = [t for t in _failed.get(ip, []) if now - t < LOCKOUT_SECONDS]
    _failed[ip] = attempts
    return len(attempts) >= MAX_ATTEMPTS


def record_failure(ip: str):
    _failed.setdefault(ip, []).append(time.time())


def clear_failures(ip: str):
    _failed.pop(ip, None)


# ---------- Sessions (token aléatoire, stocké hashé en base) ----------

def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(user_id: int, mfa_pending: bool) -> str:
    token = secrets.token_urlsafe(32)
    with get_db() as db:
        db.execute("DELETE FROM sessions WHERE expires_at < ?", (time.time(),))
        db.execute(
            "INSERT INTO sessions (token_hash, user_id, mfa_pending, expires_at) VALUES (?, ?, ?, ?)",
            (_hash_token(token), user_id, int(mfa_pending), time.time() + SESSION_LIFETIME),
        )
    return token


def get_session(token: str | None):
    """Retourne (user_row, mfa_pending) ou None."""
    if not token:
        return None
    with get_db() as db:
        row = db.execute(
            """SELECT s.mfa_pending, u.* FROM sessions s
               JOIN users u ON u.id = s.user_id
               WHERE s.token_hash = ? AND s.expires_at > ?""",
            (_hash_token(token), time.time()),
        ).fetchone()
    return row


def complete_mfa(token: str):
    with get_db() as db:
        db.execute("UPDATE sessions SET mfa_pending = 0 WHERE token_hash = ?", (_hash_token(token),))


def destroy_session(token: str | None):
    if token:
        with get_db() as db:
            db.execute("DELETE FROM sessions WHERE token_hash = ?", (_hash_token(token),))


# ---------- TOTP ----------

def new_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(username: str, secret: str) -> str:
    return pyotp.totp.TOTP(secret).provisioning_uri(name=username, issuer_name="PatchPilot")


def verify_totp(secret: str, code: str) -> bool:
    code = (code or "").strip().replace(" ", "")
    if not code.isdigit():
        return False
    return pyotp.TOTP(secret).verify(code, valid_window=1)


# ---------- Utilisateurs ----------

def create_user(username: str, password: str):
    with get_db() as db:
        db.execute(
            "INSERT INTO users (username, password_hash, totp_secret) VALUES (?, ?, ?)",
            (username, hash_password(password), new_totp_secret()),
        )


def get_user_by_name(username: str):
    with get_db() as db:
        return db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
