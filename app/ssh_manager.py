"""PatchPilot - SSH execution.

Only 3 commands are allowed (strict whitelist):
  - apt-get update
  - apt-get upgrade -y
  - apt-get full-upgrade -y
No other command can ever be sent to the managed machines.

Host-key verification (TOFU):
  The first successful connection to a machine records its host key in
  data/keys/known_hosts (trust on first use). Every later connection is
  verified against that file, so a man-in-the-middle presenting a different
  key is rejected. Use the "Test" button to (re)establish trust for a new or
  rekeyed machine.
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
}

CONNECT_TIMEOUT = 15
COMMAND_TIMEOUT = 3600  # 1 hour max per command
MAX_OS_INFO = 200       # truncate host-controlled OS string before storing

KNOWN_HOSTS_PATH = os.path.join(KEYS_DIR, "known_hosts")

# Max simultaneous SSH connections for "update all"
MAX_PARALLEL = 10
_semaphore = asyncio.Semaphore(MAX_PARALLEL)


def build_command(action: str, username: str) -> str:
    base = ACTIONS[action]  # KeyError if action is not whitelisted => rejected
    cmd = f"DEBIAN_FRONTEND=noninteractive {base}"
    if username != "root":
        cmd = "sudo -n " + cmd
    return cmd


def _host_token(host: str, port: int) -> str:
    return host if port == 22 else f"[{host}]:{port}"


def _host_is_known(host: str, port: int) -> bool:
    """True if known_hosts already has an entry for this host[:port]."""
    if not os.path.exists(KNOWN_HOSTS_PATH):
        return False
    token = _host_token(host, port)
    with open(KNOWN_HOSTS_PATH, encoding="utf-8") as f:
        for line in f:
            if line.strip() and line.split()[0] == token:
                return True
    return False


async def _connect(machine, *, learn: bool = False) -> asyncssh.SSHClientConnection:
    """Open an SSH connection.

    - Normal mode (run_action): always verify against known_hosts; an unknown
      or mismatched key raises HostKeyNotVerifiable.
    - learn=True (Test button): if the host is already known, verify strictly
      (so a changed key is caught as a possible MITM); if it is brand new,
      connect once without verification only to capture and persist its key.
    """
    host, port = machine["host"], machine["port"]

    if learn and not _host_is_known(host, port):
        # First time we see this host: capture the key (trust on first use).
        conn = await asyncio.wait_for(
            asyncssh.connect(
                host=host, port=port, username=machine["username"],
                client_keys=[SSH_KEY_PATH],
                known_hosts=None,
            ),
            timeout=CONNECT_TIMEOUT,
        )
        _remember_host_key(host, port, conn)
        return conn

    # Host already known (or normal run): enforce verification.
    return await asyncio.wait_for(
        asyncssh.connect(
            host=host, port=port, username=machine["username"],
            client_keys=[SSH_KEY_PATH],
            known_hosts=KNOWN_HOSTS_PATH,
        ),
        timeout=CONNECT_TIMEOUT,
    )


def _remember_host_key(host: str, port: int, conn: asyncssh.SSHClientConnection):
    """Append the server's host key to known_hosts if not already present."""
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
        # Never let host-key bookkeeping break the connection result.
        pass


async def test_machine(machine) -> dict:
    """Test the connection, learn/verify the host key, detect the OS and
    check privileges (root or sudo -n)."""
    try:
        async with await _connect(machine, learn=True) as conn:
            res = await conn.run(". /etc/os-release && echo \"$PRETTY_NAME\"", check=False)
            os_info = ((res.stdout or "").strip() or "Unknown OS")[:MAX_OS_INFO]

            if machine["username"] != "root":
                sudo = await conn.run("sudo -n true", check=False)
                if sudo.exit_status != 0:
                    return {
                        "ok": False, "os_info": os_info,
                        "error": "passwordless sudo (NOPASSWD) not configured for this user",
                    }
            return {"ok": True, "os_info": os_info}
    except asyncio.TimeoutError:
        return {"ok": False, "error": "Connection timed out"}
    except asyncssh.HostKeyNotVerifiable:
        return {"ok": False, "error": "Host key changed or not verifiable (possible MITM) — "
                                      "remove the old key from data/keys/known_hosts if the host was legitimately rebuilt"}
    except (OSError, asyncssh.Error) as e:
        return {"ok": False, "error": str(e)}


async def run_action(machine, action: str, on_line) -> dict:
    """Run a whitelisted action and stream each output line via on_line(str).

    Returns {"ok": bool, "exit_status": int | None, "error": str | None}.
    """
    cmd = build_command(action, machine["username"])
    async with _semaphore:
        try:
            async with await _connect(machine) as conn:
                async with conn.create_process(cmd, stderr=asyncssh.STDOUT) as proc:

                    async def _stream():
                        async for line in proc.stdout:
                            await on_line(line.rstrip("\n"))

                    try:
                        await asyncio.wait_for(_stream(), timeout=COMMAND_TIMEOUT)
                    except asyncio.TimeoutError:
                        proc.terminate()
                        return {"ok": False, "exit_status": None, "error": "Command timed out"}
                exit_status = proc.exit_status
                if exit_status == 0:
                    return {"ok": True, "exit_status": 0, "error": None}
                err = f"Exit code {exit_status}"
                if exit_status == 1 and machine["username"] != "root":
                    err += " (check sudo NOPASSWD configuration)"
                return {"ok": False, "exit_status": exit_status, "error": err}
        except asyncio.TimeoutError:
            return {"ok": False, "exit_status": None, "error": "Connection timed out"}
        except asyncssh.HostKeyNotVerifiable:
            return {"ok": False, "exit_status": None,
                    "error": "Host key not verified — run Test first to establish trust"}
        except (OSError, asyncssh.Error) as e:
            return {"ok": False, "exit_status": None, "error": str(e)}


def get_public_key() -> str:
    try:
        with open(SSH_KEY_PATH + ".pub", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""
