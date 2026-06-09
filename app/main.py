"""PatchPilot - FastAPI application: API, WebSocket and web pages."""
import asyncio
import base64
import io
import ipaddress
import os
import re
import time
import uuid

import qrcode
from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import auth, ssh_manager
from .database import get_db, init_db
from .version import GITHUB_REPO, VERSION

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_SECURE = os.environ.get("PATCHPILOT_COOKIE_SECURE", "0") == "1"
# Public origin of the site, used for WebSocket Origin checks (e.g.
# "https://patchpilot.example.com"). Set by install.sh; empty disables the check.
SITE_ORIGIN = os.environ.get("PATCHPILOT_ORIGIN", "").rstrip("/")

app = FastAPI(title="PatchPilot", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


@app.on_event("startup")
def _startup():
    init_db()


# =====================================================================
# Security headers (defense-in-depth)
# =====================================================================

@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    # script-src stays strict ('self' only) — this is the key XSS defense.
    # style-src allows inline style attributes (low risk, cannot execute JS),
    # which the templates rely on (e.g. show/hide the MFA field).
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline'; script-src 'self'; "
        "connect-src 'self' ws: wss:; frame-ancestors 'none'; base-uri 'none'"
    )
    if COOKIE_SECURE:
        resp.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return resp


# =====================================================================
# Authentication dependencies
# =====================================================================

def current_session(pp_session: str | None = Cookie(default=None)):
    row = auth.get_session(pp_session)
    if row is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return row


def current_user(row=Depends(current_session)):
    if row["mfa_pending"]:
        raise HTTPException(status_code=401, detail="MFA required")
    return row


def csrf_protect(request: Request, pp_session: str | None = Cookie(default=None)):
    """Double-submit CSRF check for unsafe methods: the X-CSRF-Token header
    must match the per-session CSRF token. Defense-in-depth on top of
    SameSite=Strict (also covers the same-site-subdomain bypass)."""
    row = auth.get_session(pp_session)
    if row is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if row["mfa_pending"]:
        raise HTTPException(status_code=401, detail="MFA required")
    header = request.headers.get(auth.CSRF_HEADER_NAME, "")
    expected = row["csrf_token"]
    if not expected or not secrets_compare(header, expected):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    return row


def secrets_compare(a: str, b: str) -> bool:
    import hmac
    return hmac.compare_digest(a or "", b or "")


def client_ip(request: Request) -> str:
    """Real client IP. uvicorn is started with --proxy-headers and
    --forwarded-allow-ips=127.0.0.1, so request.client.host already reflects
    nginx's X-Forwarded-For only when it comes from the trusted local proxy."""
    return request.client.host if request.client else "?"


def _set_session_cookie(response: Response, token: str, csrf: str, mfa_pending: bool):
    max_age = auth.MFA_PENDING_LIFETIME if mfa_pending else auth.SESSION_LIFETIME
    response.set_cookie(
        auth.COOKIE_NAME, token,
        httponly=True, samesite="strict", secure=COOKIE_SECURE,
        max_age=max_age, path="/",
    )
    # CSRF cookie is readable by JS (not HttpOnly) so the frontend can echo it
    # back in the X-CSRF-Token header.
    response.set_cookie(
        auth.CSRF_COOKIE_NAME, csrf,
        httponly=False, samesite="strict", secure=COOKIE_SECURE,
        max_age=max_age, path="/",
    )


# =====================================================================
# Pages
# =====================================================================

def _page(name: str) -> FileResponse:
    return FileResponse(os.path.join(BASE_DIR, "templates", name))


@app.get("/", response_class=HTMLResponse)
def index(pp_session: str | None = Cookie(default=None)):
    row = auth.get_session(pp_session)
    if row is None:
        return RedirectResponse("/login")
    if row["mfa_pending"]:
        return RedirectResponse("/mfa")
    return _page("index.html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(os.path.join(BASE_DIR, "static", "favicon.svg"),
                        media_type="image/svg+xml")


@app.get("/login", response_class=HTMLResponse)
def login_page():
    return _page("login.html")


@app.get("/mfa", response_class=HTMLResponse)
def mfa_page(row=Depends(current_session)):
    return _page("mfa.html")


# =====================================================================
# API: authentication
# =====================================================================

class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    totp_code: str | None = Field(default=None, max_length=10)


@app.post("/api/login")
def api_login(body: LoginBody, request: Request):
    ip = client_ip(request)
    if auth.is_locked(ip):
        raise HTTPException(status_code=429, detail="Too many attempts. Try again in 15 minutes.")

    user = auth.get_user_by_name(body.username.strip())
    if user is None or not auth.verify_password(body.password, user["password_hash"]):
        auth.record_failure(ip)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if user["pending"]:
        raise HTTPException(status_code=403, detail="Account not activated yet")

    if user["totp_enabled"]:
        if not body.totp_code:
            return {"mfa_code_required": True}
        ok = auth.verify_totp(user["totp_secret"], body.totp_code) or \
            auth.verify_and_consume_recovery(user["id"], body.totp_code)
        if not ok:
            auth.record_failure(ip)
            raise HTTPException(status_code=401, detail="Invalid MFA code")
        auth.clear_failures(ip)
        token, csrf = auth.create_session(user["id"], mfa_pending=False)
        resp = JSONResponse({"ok": True, "redirect": "/"})
        _set_session_cookie(resp, token, csrf, mfa_pending=False)
        return resp

    # First login: MFA setup is mandatory (short-lived pending session)
    auth.clear_failures(ip)
    token, csrf = auth.create_session(user["id"], mfa_pending=True)
    resp = JSONResponse({"ok": True, "redirect": "/mfa"})
    _set_session_cookie(resp, token, csrf, mfa_pending=True)
    return resp


@app.get("/api/mfa/qr")
def api_mfa_qr(row=Depends(current_session)):
    if row["totp_enabled"]:
        raise HTTPException(status_code=400, detail="MFA already enabled")
    # Secret is generated lazily here, only at first setup — never stored
    # eagerly at account creation.
    secret = auth.get_or_create_totp_secret(row["id"], row["totp_secret"])
    uri = auth.totp_uri(row["username"], secret)
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return {"qr": f"data:image/png;base64,{b64}", "secret": secret}


class MfaBody(BaseModel):
    code: str = Field(min_length=6, max_length=10)


@app.post("/api/mfa/verify")
def api_mfa_verify(body: MfaBody, request: Request,
                   pp_session: str | None = Cookie(default=None)):
    row = auth.get_session(pp_session)
    if row is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    # For an already-enabled account, a CSRF token is required (this is a
    # state-changing, session-rotating call). During first-time setup the
    # session is fresh and has no prior CSRF context, so it is exempt.
    if row["totp_enabled"]:
        header = request.headers.get(auth.CSRF_HEADER_NAME, "")
        if not secrets_compare(header, row["csrf_token"]):
            raise HTTPException(status_code=403, detail="Invalid CSRF token")

    secret = row["totp_secret"]
    if not secret or not auth.verify_totp(secret, body.code):
        raise HTTPException(status_code=401, detail="Invalid code")

    recovery_codes = None
    first_setup = not row["totp_enabled"]
    if first_setup:
        with get_db() as db:
            db.execute("UPDATE users SET totp_enabled = 1 WHERE id = ?", (row["id"],))
        # Generate one-time recovery codes, shown once now.
        recovery_codes = auth.generate_recovery_codes(row["id"])

    # Rotate the token: kill the pending session, issue a fresh full one.
    token, csrf = auth.complete_mfa(pp_session, row["id"])
    resp = JSONResponse({"ok": True, "redirect": "/", "recovery_codes": recovery_codes})
    _set_session_cookie(resp, token, csrf, mfa_pending=False)
    return resp


@app.post("/api/logout")
def api_logout(pp_session: str | None = Cookie(default=None)):
    auth.destroy_session(pp_session)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.COOKIE_NAME, path="/")
    resp.delete_cookie(auth.CSRF_COOKIE_NAME, path="/")
    return resp


# =====================================================================
# API: machines
# =====================================================================

HOSTNAME_RE = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9.-]{0,253})$")
USERNAME_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")


class MachineBody(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(default="root", max_length=32)

    @field_validator("host")
    @classmethod
    def check_host(cls, v: str) -> str:
        v = v.strip()
        try:
            ipaddress.ip_address(v)
            return v
        except ValueError:
            pass
        if not HOSTNAME_RE.match(v):
            raise ValueError("Invalid host (IP address or hostname expected)")
        return v

    @field_validator("username")
    @classmethod
    def check_username(cls, v: str) -> str:
        if not USERNAME_RE.match(v):
            raise ValueError("Invalid Unix username")
        return v


@app.get("/api/machines")
def api_machines(user=Depends(current_user)):
    with get_db() as db:
        rows = db.execute("SELECT * FROM machines ORDER BY name").fetchall()
    return [dict(r) for r in rows]


@app.post("/api/machines")
def api_add_machine(body: MachineBody, user=Depends(csrf_protect)):
    with get_db() as db:
        try:
            cur = db.execute(
                "INSERT INTO machines (name, host, port, username) VALUES (?, ?, ?, ?)",
                (body.name.strip(), body.host, body.port, body.username),
            )
        except Exception:
            raise HTTPException(status_code=409, detail="This machine already exists")
        return {"ok": True, "id": cur.lastrowid}


@app.delete("/api/machines/{machine_id}")
def api_delete_machine(machine_id: int, user=Depends(csrf_protect)):
    with get_db() as db:
        db.execute("DELETE FROM machines WHERE id = ?", (machine_id,))
    return {"ok": True}


def _get_machine(machine_id: int):
    with get_db() as db:
        row = db.execute("SELECT * FROM machines WHERE id = ?", (machine_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Machine not found")
    return row


@app.post("/api/machines/{machine_id}/test")
async def api_test_machine(machine_id: int, user=Depends(csrf_protect)):
    machine = _get_machine(machine_id)
    result = await ssh_manager.test_machine(machine)
    if result.get("os_info"):
        with get_db() as db:
            db.execute("UPDATE machines SET os_info = ? WHERE id = ?", (result["os_info"], machine_id))
    return result


@app.get("/api/public-key")
def api_public_key(user=Depends(current_user)):
    return {"public_key": ssh_manager.get_public_key()}


@app.get("/api/me")
def api_me(user=Depends(current_user)):
    return {"username": user["username"], "is_admin": bool(user["is_admin"])}


@app.get("/api/mfa/recovery/status")
def api_recovery_status(user=Depends(current_user)):
    return {"enabled": bool(user["totp_enabled"]),
            "remaining": auth.count_recovery_codes(user["id"])}


class RegenBody(BaseModel):
    code: str = Field(min_length=6, max_length=20)


@app.post("/api/mfa/recovery/regenerate")
def api_recovery_regenerate(body: RegenBody, user=Depends(csrf_protect)):
    if not user["totp_enabled"]:
        raise HTTPException(status_code=400, detail="MFA is not enabled")
    # Re-confirm identity with a current TOTP code before invalidating old codes.
    if not auth.verify_totp(user["totp_secret"], body.code):
        raise HTTPException(status_code=401, detail="Invalid MFA code")
    codes = auth.generate_recovery_codes(user["id"])
    return {"ok": True, "recovery_codes": codes}


# =====================================================================
# API: user management (admin only)
# =====================================================================

def current_admin(request: Request, user=Depends(csrf_protect)):
    if not user["is_admin"]:
        raise HTTPException(status_code=403, detail="Administrator privileges required")
    return user


def current_admin_get(user=Depends(current_user)):
    """Admin check for safe (GET) requests, without CSRF."""
    if not user["is_admin"]:
        raise HTTPException(status_code=403, detail="Administrator privileges required")
    return user


USERNAME_ACCOUNT_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class NewUserBody(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    is_admin: bool = False

    @field_validator("username")
    @classmethod
    def check_username(cls, v: str) -> str:
        v = v.strip()
        if not USERNAME_ACCOUNT_RE.match(v):
            raise ValueError("Username may only contain letters, digits, dot, dash and underscore")
        return v


def _activation_link(request: Request, token: str) -> str:
    base = SITE_ORIGIN or str(request.base_url).rstrip("/")
    return f"{base}/activate?token={token}"


@app.get("/api/users")
def api_list_users(admin=Depends(current_admin_get)):
    rows = auth.list_users()
    return [dict(r) for r in rows]


@app.post("/api/users")
def api_create_user(body: NewUserBody, request: Request, admin=Depends(current_admin)):
    if auth.get_user_by_name(body.username):
        raise HTTPException(status_code=409, detail="This username already exists")
    token = auth.create_pending_user(body.username, is_admin=body.is_admin)
    return {"ok": True, "activation_link": _activation_link(request, token)}


@app.post("/api/users/{user_id}/reinvite")
def api_reinvite(user_id: int, request: Request, admin=Depends(current_admin)):
    target = auth.get_user_by_id(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if not target["pending"]:
        raise HTTPException(status_code=400, detail="This account is already active")
    token = auth.regenerate_activation(user_id)
    return {"ok": True, "activation_link": _activation_link(request, token)}


@app.delete("/api/users/{user_id}")
def api_delete_user(user_id: int, admin=Depends(current_admin)):
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    target = auth.get_user_by_id(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    # Don't allow removing the last remaining admin.
    if target["is_admin"]:
        admins = [u for u in auth.list_users() if u["is_admin"]]
        if len(admins) <= 1:
            raise HTTPException(status_code=400, detail="Cannot delete the last administrator")
    auth.delete_user(user_id)
    return {"ok": True}


# =====================================================================
# Account activation (public, secured by the invitation token)
# =====================================================================

@app.get("/activate", response_class=HTMLResponse)
def activate_page():
    return _page("activate.html")


@app.get("/api/activation/info")
def api_activation_info(token: str = ""):
    user = auth.get_pending_by_token(token)
    if user is None:
        raise HTTPException(status_code=404, detail="Invalid or expired activation link")
    return {"username": user["username"]}


class ActivationBody(BaseModel):
    token: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=10, max_length=256)


@app.post("/api/activation/complete")
def api_activation_complete(body: ActivationBody):
    # Public endpoint, protected by the unguessable single-use token.
    if auth.get_pending_by_token(body.token) is None:
        raise HTTPException(status_code=404, detail="Invalid or expired activation link")
    auth.activate_user(body.token, body.password)
    return {"ok": True, "redirect": "/login"}


# =====================================================================
# API: version / update check (against the latest GitHub release)
# =====================================================================

_version_cache = {"ts": 0.0, "latest": None}
VERSION_CACHE_TTL = 3600  # check GitHub at most once per hour


def _fetch_latest_release() -> str | None:
    import json as _json
    import urllib.request
    req = urllib.request.Request(
        f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "PatchPilot"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return _json.load(r).get("tag_name")


def _parse_version(v: str):
    return tuple(int(x) for x in v.strip().lstrip("vV").split("."))


@app.get("/api/version")
async def api_version(user=Depends(current_user)):
    now = time.time()
    if now - _version_cache["ts"] > VERSION_CACHE_TTL:
        try:
            _version_cache["latest"] = await asyncio.to_thread(_fetch_latest_release)
        except Exception:
            _version_cache["latest"] = None
        _version_cache["ts"] = now

    latest = _version_cache["latest"]
    up_to_date = None
    if latest:
        try:
            up_to_date = _parse_version(VERSION) >= _parse_version(latest)
        except ValueError:
            up_to_date = None
    return {
        "version": VERSION,
        "latest": latest,
        "up_to_date": up_to_date,
        "releases_url": f"https://github.com/{GITHUB_REPO}/releases",
    }


# =====================================================================
# Update jobs + WebSocket (real-time logs)
# =====================================================================

jobs: dict[str, dict] = {}
ws_clients: set[WebSocket] = set()


async def _broadcast(event: dict):
    dead = []
    for ws in ws_clients:
        try:
            await ws.send_json(event)
        except Exception:
            dead.append(ws)
    for ws in dead:
        ws_clients.discard(ws)


async def _run_job(job_id: str, machine, action: str):
    jobs[job_id]["status"] = "running"
    await _broadcast({"type": "status", "job_id": job_id, "machine_id": machine["id"],
                      "machine_name": machine["name"], "action": action, "status": "running"})

    async def on_line(line: str):
        await _broadcast({"type": "line", "job_id": job_id, "machine_id": machine["id"],
                          "machine_name": machine["name"], "line": line})

    result = await ssh_manager.run_action(machine, action, on_line)
    status = "success" if result["ok"] else "error"
    jobs[job_id]["status"] = status

    with get_db() as db:
        db.execute(
            "UPDATE machines SET last_action = ?, last_status = ?, last_run = datetime('now', 'localtime') WHERE id = ?",
            (action, status, machine["id"]),
        )
    await _broadcast({"type": "status", "job_id": job_id, "machine_id": machine["id"],
                      "machine_name": machine["name"], "action": action, "status": status,
                      "error": result.get("error")})


class RunBody(BaseModel):
    action: str

    @field_validator("action")
    @classmethod
    def check_action(cls, v: str) -> str:
        if v not in ssh_manager.ACTIONS:
            raise ValueError("Action not allowed")
        return v


def _machine_busy(machine_id: int) -> bool:
    return any(j["machine_id"] == machine_id and j["status"] in ("pending", "running")
               for j in jobs.values())


_background_tasks: set = set()


def _prune_jobs():
    """Keep only the most recent finished jobs to bound memory."""
    finished = [(jid, j) for jid, j in jobs.items() if j["status"] in ("success", "error")]
    if len(finished) > 200:
        finished.sort(key=lambda kv: kv[1]["started"])
        for jid, _ in finished[:-200]:
            jobs.pop(jid, None)


def _start_job(machine, action: str) -> str:
    job_id = uuid.uuid4().hex[:12]
    jobs[job_id] = {"machine_id": machine["id"], "action": action,
                    "status": "pending", "started": time.time()}
    task = asyncio.create_task(_run_job(job_id, machine, action))
    _background_tasks.add(task)
    task.add_done_callback(lambda t: (_background_tasks.discard(t), _prune_jobs()))
    return job_id


@app.post("/api/machines/{machine_id}/run")
async def api_run(machine_id: int, body: RunBody, user=Depends(csrf_protect)):
    machine = _get_machine(machine_id)
    if _machine_busy(machine_id):
        raise HTTPException(status_code=409, detail="An update is already running on this machine")
    return {"ok": True, "job_id": _start_job(machine, body.action)}


@app.post("/api/run-all")
async def api_run_all(body: RunBody, user=Depends(csrf_protect)):
    with get_db() as db:
        machines = db.execute("SELECT * FROM machines ORDER BY name").fetchall()
    started = []
    for m in machines:
        if not _machine_busy(m["id"]):
            started.append(_start_job(m, body.action))
    return {"ok": True, "job_ids": started, "count": len(started)}


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    # Origin check (anti cross-site WebSocket hijacking). Only enforced when
    # PATCHPILOT_ORIGIN is configured.
    if SITE_ORIGIN:
        origin = (websocket.headers.get("origin") or "").rstrip("/")
        if origin != SITE_ORIGIN:
            await websocket.close(code=4403)
            return
    token = websocket.cookies.get(auth.COOKIE_NAME)
    row = auth.get_session(token)
    if row is None or row["mfa_pending"]:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    ws_clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()  # keepalive / content ignored
    except WebSocketDisconnect:
        pass
    finally:
        ws_clients.discard(websocket)
