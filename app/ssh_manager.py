"""PatchPilot - SSH execution.

Only 3 commands are allowed (strict whitelist):
  - apt-get update
  - apt-get upgrade -y
  - apt-get full-upgrade -y
No other command can ever be sent to the managed machines.
"""
import asyncio

import asyncssh

from .database import SSH_KEY_PATH

# STRICT whitelist — never build a command from user input.
ACTIONS = {
    "update": "apt-get update",
    "upgrade": "apt-get upgrade -y",
    "full-upgrade": "apt-get full-upgrade -y",
}

CONNECT_TIMEOUT = 15
COMMAND_TIMEOUT = 3600  # 1 hour max per command

# Max simultaneous SSH connections for "update all"
MAX_PARALLEL = 10
_semaphore = asyncio.Semaphore(MAX_PARALLEL)


def build_command(action: str, username: str) -> str:
    base = ACTIONS[action]  # KeyError if action is not whitelisted => rejected
    cmd = f"DEBIAN_FRONTEND=noninteractive {base}"
    if username != "root":
        cmd = "sudo -n " + cmd
    return cmd


async def _connect(machine) -> asyncssh.SSHClientConnection:
    return await asyncio.wait_for(
        asyncssh.connect(
            host=machine["host"],
            port=machine["port"],
            username=machine["username"],
            client_keys=[SSH_KEY_PATH],
            known_hosts=None,  # internal fleet; see README to harden
        ),
        timeout=CONNECT_TIMEOUT,
    )


async def test_machine(machine) -> dict:
    """Test the connection, detect the OS and check privileges (root or sudo -n)."""
    try:
        async with await _connect(machine) as conn:
            res = await conn.run(". /etc/os-release && echo \"$PRETTY_NAME\"", check=False)
            os_info = (res.stdout or "").strip() or "Unknown OS"

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
        except (OSError, asyncssh.Error) as e:
            return {"ok": False, "exit_status": None, "error": str(e)}


def get_public_key() -> str:
    try:
        with open(SSH_KEY_PATH + ".pub", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""
