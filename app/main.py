"""PatchPilot - Application FastAPI : API, WebSocket et pages web."""
import asyncio
import base64
import io
import ipaddress
import re
import secrets
import time
import uuid

import qrcode
from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import auth, ssh_manager
from .database import get_db, init_db

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_SECURE = os.environ.get("PATCHPILOT_COOKIE_SECURE", "0") == "1"

app = FastAPI(title="PatchPilot", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


@app.on_event("startup")
def _startup():
    init_db()


# =====================================================================
# Dépendances d'authentification
# =====================================================================

def current_session(pp_session: str | None = Cookie(default=None)):
    row = auth.get_session(pp_session)
    if row is None:
        raise HTTPException(status_code=401, detail="Non authentifié")
    return row


def current_user(row=Depends(current_session)):
    if row["mfa_pending"]:
        raise HTTPException(status_code=401, detail="MFA requis")
    return row


def _set_session_cookie(response: Response, token: str):
    response.set_cookie(
        auth.COOKIE_NAME, token,
        httponly=True, samesite="strict", secure=COOKIE_SECURE,
        max_age=auth.SESSION_LIFETIME, path="/",
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


@app.get("/login", response_class=HTMLResponse)
def login_page():
    return _page("login.html")


@app.get("/mfa", response_class=HTMLResponse)
def mfa_page(row=Depends(current_session)):
    return _page("mfa.html")


# =====================================================================
# API : authentification
# =====================================================================

class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    totp_code: str | None = Field(default=None, max_length=10)


@app.post("/api/login")
def api_login(body: LoginBody, request: Request):
    ip = request.client.host if request.client else "?"
    if auth.is_locked(ip):
        raise HTTPException(status_code=429, detail="Trop de tentatives. Réessayez dans 15 minutes.")

    user = auth.get_user_by_name(body.username.strip())
    if user is None or not auth.verify_password(body.password, user["password_hash"]):
        auth.record_failure(ip)
        raise HTTPException(status_code=401, detail="Identifiants invalides")

    if user["totp_enabled"]:
        if not body.totp_code:
            return {"mfa_code_required": True}
        if not auth.verify_totp(user["totp_secret"], body.totp_code):
            auth.record_failure(ip)
            raise HTTPException(status_code=401, detail="Code MFA invalide")
        auth.clear_failures(ip)
        token = auth.create_session(user["id"], mfa_pending=False)
        resp = JSONResponse({"ok": True, "redirect": "/"})
        _set_session_cookie(resp, token)
        return resp

    # Premier login : configuration du MFA obligatoire
    auth.clear_failures(ip)
    token = auth.create_session(user["id"], mfa_pending=True)
    resp = JSONResponse({"ok": True, "redirect": "/mfa"})
    _set_session_cookie(resp, token)
    return resp


@app.get("/api/mfa/qr")
def api_mfa_qr(row=Depends(current_session)):
    if row["totp_enabled"]:
        raise HTTPException(status_code=400, detail="MFA déjà activé")
    uri = auth.totp_uri(row["username"], row["totp_secret"])
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return {"qr": f"data:image/png;base64,{b64}", "secret": row["totp_secret"]}


class MfaBody(BaseModel):
    code: str = Field(min_length=6, max_length=10)


@app.post("/api/mfa/verify")
def api_mfa_verify(body: MfaBody, row=Depends(current_session),
                   pp_session: str | None = Cookie(default=None)):
    if not auth.verify_totp(row["totp_secret"], body.code):
        raise HTTPException(status_code=401, detail="Code invalide")
    if not row["totp_enabled"]:
        with get_db() as db:
            db.execute("UPDATE users SET totp_enabled = 1 WHERE id = ?", (row["id"],))
    auth.complete_mfa(pp_session)
    return {"ok": True, "redirect": "/"}


@app.post("/api/logout")
def api_logout(pp_session: str | None = Cookie(default=None)):
    auth.destroy_session(pp_session)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.COOKIE_NAME, path="/")
    return resp


# =====================================================================
# API : machines
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
            raise ValueError("Hôte invalide (IP ou nom d'hôte attendu)")
        return v

    @field_validator("username")
    @classmethod
    def check_username(cls, v: str) -> str:
        if not USERNAME_RE.match(v):
            raise ValueError("Nom d'utilisateur Unix invalide")
        return v


@app.get("/api/machines")
def api_machines(user=Depends(current_user)):
    with get_db() as db:
        rows = db.execute("SELECT * FROM machines ORDER BY name").fetchall()
    return [dict(r) for r in rows]


@app.post("/api/machines")
def api_add_machine(body: MachineBody, user=Depends(current_user)):
    with get_db() as db:
        try:
            cur = db.execute(
                "INSERT INTO machines (name, host, port, username) VALUES (?, ?, ?, ?)",
                (body.name.strip(), body.host, body.port, body.username),
            )
        except Exception:
            raise HTTPException(status_code=409, detail="Cette machine existe déjà")
        return {"ok": True, "id": cur.lastrowid}


@app.delete("/api/machines/{machine_id}")
def api_delete_machine(machine_id: int, user=Depends(current_user)):
    with get_db() as db:
        db.execute("DELETE FROM machines WHERE id = ?", (machine_id,))
    return {"ok": True}


def _get_machine(machine_id: int):
    with get_db() as db:
        row = db.execute("SELECT * FROM machines WHERE id = ?", (machine_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Machine introuvable")
    return row


@app.post("/api/machines/{machine_id}/test")
async def api_test_machine(machine_id: int, user=Depends(current_user)):
    machine = _get_machine(machine_id)
    result = await ssh_manager.test_machine(machine)
    if result.get("os_info"):
        with get_db() as db:
            db.execute("UPDATE machines SET os_info = ? WHERE id = ?", (result["os_info"], machine_id))
    return result


@app.get("/api/public-key")
def api_public_key(user=Depends(current_user)):
    return {"public_key": ssh_manager.get_public_key()}


# =====================================================================
# Jobs de mise à jour + WebSocket (logs en temps réel)
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
            raise ValueError("Action non autorisée")
        return v


def _machine_busy(machine_id: int) -> bool:
    return any(j["machine_id"] == machine_id and j["status"] in ("pending", "running")
               for j in jobs.values())


def _start_job(machine, action: str) -> str:
    job_id = uuid.uuid4().hex[:12]
    jobs[job_id] = {"machine_id": machine["id"], "action": action,
                    "status": "pending", "started": time.time()}
    asyncio.get_event_loop().create_task(_run_job(job_id, machine, action))
    return job_id


@app.post("/api/machines/{machine_id}/run")
async def api_run(machine_id: int, body: RunBody, user=Depends(current_user)):
    machine = _get_machine(machine_id)
    if _machine_busy(machine_id):
        raise HTTPException(status_code=409, detail="Une mise à jour est déjà en cours sur cette machine")
    return {"ok": True, "job_id": _start_job(machine, body.action)}


@app.post("/api/run-all")
async def api_run_all(body: RunBody, user=Depends(current_user)):
    with get_db() as db:
        machines = db.execute("SELECT * FROM machines ORDER BY name").fetchall()
    started = []
    for m in machines:
        if not _machine_busy(m["id"]):
            started.append(_start_job(m, body.action))
    return {"ok": True, "job_ids": started, "count": len(started)}


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    token = websocket.cookies.get(auth.COOKIE_NAME)
    row = auth.get_session(token)
    if row is None or row["mfa_pending"]:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    ws_clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()  # keepalive / on ignore le contenu
    except WebSocketDisconnect:
        pass
    finally:
        ws_clients.discard(websocket)
