"""PatchPilot - Authentication: bcrypt + server-side sessions + TOTP MFA."""
import hashlib
import secrets
import time

import bcrypt
import pyotp

from .database import get_db

SESSION_LIFETIME = 12 * 3600     # 12 hours for a fully authenticated session
MFA_PENDING_LIFETIME = 600       # 10 minutes to complete MFA before re-login
COOKIE_NAME = "pp_session"
CSRF_COOKIE_NAME = "pp_csrf"
CSRF_HEADER_NAME = "x-csrf-token"

# Brute-force protection: 5 failures => 15 min lockout (per IP)
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 900
_failed: dict[str, list[float]] = {}


# ---------- Passwords ----------

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False


# ---------- Brute-force protection ----------

def is_locked(ip: str) -> bool:
    now = time.time()
    attempts = [t for t in _failed.get(ip, []) if now - t < LOCKOUT_SECONDS]
    _failed[ip] = attempts
    return len(attempts) >= MAX_ATTEMPTS


def record_failure(ip: str):
    _failed.setdefault(ip, []).append(time.time())


def clear_failures(ip: str):
    _failed.pop(ip, None)


# ---------- Sessions (random token, stored hashed in DB) ----------

def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(user_id: int, mfa_pending: bool) -> tuple[str, str]:
    """Create a session. Returns (session_token, csrf_token).

    MFA-pending sessions get a short lifetime; fully authenticated ones the
    full lifetime.
    """
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    ttl = MFA_PENDING_LIFETIME if mfa_pending else SESSION_LIFETIME
    with get_db() as db:
        db.execute("DELETE FROM sessions WHERE expires_at < ?", (time.time(),))
        db.execute(
            "INSERT INTO sessions (token_hash, csrf_token, user_id, mfa_pending, expires_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (_hash_token(token), csrf, user_id, int(mfa_pending), time.time() + ttl),
        )
    return token, csrf


def get_session(token: str | None):
    """Return (session row joined with user) or None."""
    if not token:
        return None
    with get_db() as db:
        row = db.execute(
            """SELECT s.mfa_pending, s.csrf_token, u.* FROM sessions s
               JOIN users u ON u.id = s.user_id
               WHERE s.token_hash = ? AND s.expires_at > ?""",
            (_hash_token(token), time.time()),
        ).fetchone()
    return row


def complete_mfa(old_token: str, user_id: int) -> tuple[str, str]:
    """Finish MFA: destroy the pending session and issue a fresh full session.

    Rotating the token prevents session-fixation. Returns the new
    (session_token, csrf_token).
    """
    destroy_session(old_token)
    return create_session(user_id, mfa_pending=False)


def destroy_session(token: str | None):
    if token:
        with get_db() as db:
            db.execute("DELETE FROM sessions WHERE token_hash = ?", (_hash_token(token),))


# ---------- TOTP ----------

def new_totp_secret() -> str:
    return pyotp.random_base32()


def get_or_create_totp_secret(user_id: int, current_secret: str | None) -> str:
    """Lazily generate the TOTP secret on first setup, so it is never created
    eagerly at account creation. Once MFA is enabled the secret is fixed."""
    if current_secret:
        return current_secret
    secret = new_totp_secret()
    with get_db() as db:
        db.execute("UPDATE users SET totp_secret = ? WHERE id = ?", (secret, user_id))
    return secret


def totp_uri(username: str, secret: str) -> str:
    return pyotp.totp.TOTP(secret).provisioning_uri(name=username, issuer_name="PatchPilot")


def verify_totp(secret: str, code: str) -> bool:
    code = (code or "").strip().replace(" ", "")
    if not code.isdigit():
        return False
    return pyotp.TOTP(secret).verify(code, valid_window=1)


# ---------- Users ----------

def create_user(username: str, password: str):
    # totp_secret stays empty until the user sets up MFA on first login.
    with get_db() as db:
        db.execute(
            "INSERT INTO users (username, password_hash, totp_secret) VALUES (?, ?, '')",
            (username, hash_password(password)),
        )


def get_user_by_name(username: str):
    with get_db() as db:
        return db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
