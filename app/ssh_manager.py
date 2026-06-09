"""PatchPilot - SSH execution.

Allowed write commands (strict whitelist — never built from user input):
  - apt-get update
  - apt-get upgrade -y
  - apt-get full-upgrade -y
  - apt-get autoremove -y
Plus a single read-only simulation used to count pending updates
(apt-get -s dist-upgrade, which changes nothing on the host).

The standard maintenance sequence is: update -> upgrade -> autoremove.

Host-key verification (TOFU): the first successful connection records the
machine's host key in data/keys/known_hosts; later connections reject a
changed key (possible MITM).
"""
import asyncio
import os

import asyncssh

from .database import KEYS_DIR, SSH_KEY_PATH

# STRICT whitelist — never build a command from user input.
ACTIONS = {
    "update": "apt-get update",
    "upgrade": "apt-get upgrade -y",
    "full-upgrade": "apt-get full-upgrade -y",
    "autoremove": "apt-get autoremove -y",
}

# Ordered maintenance sequence run by the "Update" button / scheduler.
SEQUENCE = ["update", "upgrade", "autoremove"]
# Read-only check: refresh lists then count what would be upgraded.
CHECK = ["update"]

CONNECT_TIMEOUT = 15
COMMAND_TIMEOUT = 3600  # 1 hour max per command
MAX_OS_INFO = 200

KNOWN_HOSTS_PATH = os.path.join(KEYS_DIR, "known_hosts")

MAX_PARALLEL = 10
_semaphore = asyncio.Semaphore(MAX_PARALLEL)


def build_command(action: str, username: str) -> str:
    base = ACTIONS[action]  # KeyError if not whitelisted => rejected
    cmd = f"DEBIAN_FRONTEND=noninteractive {base}"
    if username != "root":
        cmd = "sudo -n " + cmd
    return cmd


def _count_command(username: str) -> str:
    # -s = simulate (read-only). Counts packages that would be upgraded.
    cmd = "apt-get -s -o Debug::NoLocking=true dist-upgrade"
    if username != "root":
        cmd = "sudo -n " + cmd
    return cmd


def _host_token(host: str, port: int) -> str:
    return host if port == 22 else f"[{host}]:{port}"


def _host_is_known(host: str, port: int) -> bool:
    if not os.path.exists(KNOWN_HOSTS_PATH):
        return False
    token = _host_token(host, port)
    with open(KNOWN_HOSTS_PATH, encoding="utf-8") as f:
        for line in f:
            if line.strip() and line.split()[0] == token:
                return True
    return False


async def _connect(machine, *, learn: bool = False) -> asyncssh.SSHClientConnection:
    host, port = machine["host"], machine["port"]
    if learn and not _host_is_known(host, port):
        conn = await asyncio.wait_for(
            asyncssh.connect(host=host, port=port, username=machine["username"],
                             client_keys=[SSH_KEY_PATH], known_hosts=None),
            timeout=CONNECT_TIMEOUT)
        _remember_host_key(host, port, conn)
        return conn
    return await asyncio.wait_for(
        asyncssh.connect(host=host, port=port, username=machine["username"],
                         client_keys=[SSH_KEY_PATH], known_hosts=KNOWN_HOSTS_PATH),
        timeout=CONNECT_TIMEOUT)


def _remember_host_key(host: str, port: int, conn: asyncssh.SSHClientConnection):
    try:
        key = conn.get_server_host_key()
        if key is None:
            return
        line = _host_token(host, port) + " " + key.export_public_key().decode().strip() + "\n"
        existing = ""
        if os.path.exists(KNOWN_HOSTS_PATH):
            with open(KNOWN_HOSTS_PATH, encoding="utf-8") as f:
                existing = f.read()
        if line.strip() in (l.strip() for l in existing.splitlines()):
            return
        with open(KNOWN_HOSTS_PATH, "a", encoding="utf-8") as f:
            f.write(line)
        os.chmod(KNOWN_HOSTS_PATH, 0o600)
    except Exception:
        pass


async def _count_pending(conn, username: str):
    """Return the number of packages that would be upgraded, or None on error."""
    try:
        res = await conn.run(_count_command(username), check=False)
        if res.exit_status != 0:
            return None
        return sum(1 for ln in (res.stdout or "").splitlines() if ln.startswith("Inst "))
    except Exception:
        return None


async def test_machine(machine) -> dict:
    """Check connectivity, learn/verify host key, detect OS, check sudo."""
    try:
        async with await _connect(machine, learn=True) as conn:
            res = await conn.run(". /etc/os-release && echo \"$PRETTY_NAME\"", check=False)
            os_info = ((res.stdout or "").strip() or "Unknown OS")[:MAX_OS_INFO]
            if machine["username"] != "root":
                sudo = await conn.run("sudo -n true", check=False)
                if sudo.exit_status != 0:
                    return {"ok": False, "os_info": os_info,
                            "error": "passwordless sudo (NOPASSWD) not configured for this user"}
            return {"ok": True, "os_info": os_info}
    except asyncio.TimeoutError:
        return {"ok": False, "error": "Connection timed out"}
    except asyncssh.HostKeyNotVerifiable:
        return {"ok": False, "error": "Host key changed or not verifiable (possible MITM) — "
                "remove the old key from data/keys/known_hosts if the host was legitimately rebuilt"}
    except (OSError, asyncssh.Error) as e:
        return {"ok": False, "error": str(e)}


async def run_sequence(machine, actions, on_line, *, count_after=True, learn=False) -> dict:
    """Run an ordered list of whitelisted actions over a single connection,
    streaming output line by line. Stops at the first failing command.

    Returns {"ok": bool, "error": str|None, "failed_action": str|None,
             "pending": int|None}.
    """
    # Validate every action against the whitelist up front.
    for a in actions:
        if a not in ACTIONS:
            return {"ok": False, "error": "Action not allowed", "failed_action": a, "pending": None}

    async with _semaphore:
        try:
            async with await _connect(machine, learn=learn) as conn:
                for action in actions:
                    cmd = build_command(action, machine["username"])
                    await on_line(f"$ {ACTIONS[action]}")
                    async with conn.create_process(cmd, stderr=asyncssh.STDOUT) as proc:
                        async def _stream():
                            async for line in proc.stdout:
                                await on_line(line.rstrip("\n"))
                        try:
                            await asyncio.wait_for(_stream(), timeout=COMMAND_TIMEOUT)
                        except asyncio.TimeoutError:
                            proc.terminate()
                            return {"ok": False, "error": "Command timed out",
                                    "failed_action": action, "pending": None}
                    if proc.exit_status != 0:
                        err = f"Exit code {proc.exit_status}"
                        if proc.exit_status == 1 and machine["username"] != "root":
                            err += " (check sudo NOPASSWD configuration)"
                        return {"ok": False, "error": err, "failed_action": action, "pending": None}

                pending = await _count_pending(conn, machine["username"]) if count_after else None
            return {"ok": True, "error": None, "failed_action": None, "pending": pending}
        except asyncio.TimeoutError:
            return {"ok": False, "error": "Connection timed out", "failed_action": None, "pending": None}
        except asyncssh.HostKeyNotVerifiable:
            return {"ok": False, "error": "Host key not verified — run Check first to establish trust",
                    "failed_action": None, "pending": None}
        except (OSError, asyncssh.Error) as e:
            return {"ok": False, "error": str(e), "failed_action": None, "pending": None}


def get_public_key() -> str:
    try:
        with open(SSH_KEY_PATH + ".pub", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""
