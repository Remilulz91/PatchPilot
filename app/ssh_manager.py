"""PatchPilot - SSH execution.

Allowed WRITE commands (strict whitelist, never built from user input):
  - apt-get update
  - apt-get upgrade -y
  - apt-get full-upgrade -y
  - apt-get autoremove -y
Plus read-only detection/simulation commands (OS detection, reboot check,
pending-update count). Those never modify the host.

OS-aware sequences:
  - Debian / Ubuntu  -> update -> upgrade      -> autoremove
  - Proxmox products -> update -> full-upgrade -> autoremove   (Proxmox requires
    dist-upgrade; plain upgrade is discouraged)
  - "Full update"    -> update -> full-upgrade -> autoremove   (any OS, explicit)
  - "Check"          -> update, then count pending (no changes)

PatchPilot never reboots a machine: it only reports when a reboot is needed.
"""
import asyncio
import os

import asyncssh

from .database import KEYS_DIR, SSH_KEY_PATH

ACTIONS = {
    "update": "apt-get update",
    "upgrade": "apt-get upgrade -y",
    "full-upgrade": "apt-get full-upgrade -y",
    "autoremove": "apt-get autoremove -y",
}
PROXMOX_TYPES = ("pve", "pbs", "pmg", "pdm")

CONNECT_TIMEOUT = 15
COMMAND_TIMEOUT = 3600
MAX_OS_INFO = 200
KNOWN_HOSTS_PATH = os.path.join(KEYS_DIR, "known_hosts")
MAX_PARALLEL = 10
_semaphore = asyncio.Semaphore(MAX_PARALLEL)

# Read-only detection: base OS, Proxmox product + version, reboot-required.
DETECT_CMD = r'''
export LC_ALL=C
. /etc/os-release 2>/dev/null; echo "BASE=$PRETTY_NAME"
if command -v pveversion >/dev/null 2>&1; then
  echo "TYPE=pve"; echo "VER=$(pveversion 2>/dev/null | head -1)"
elif dpkg-query -W -f='${Status}' proxmox-backup-server 2>/dev/null | grep -q "install ok installed"; then
  echo "TYPE=pbs"; echo "VER=$(dpkg-query -W -f='${Version}' proxmox-backup-server 2>/dev/null)"
elif command -v pmgversion >/dev/null 2>&1; then
  echo "TYPE=pmg"; echo "VER=$(pmgversion 2>/dev/null | head -1)"
elif dpkg-query -W -f='${Status}' proxmox-datacenter-manager 2>/dev/null | grep -q "install ok installed"; then
  echo "TYPE=pdm"; echo "VER=$(dpkg-query -W -f='${Version}' proxmox-datacenter-manager 2>/dev/null)"
else
  echo "TYPE=base"
fi
RR=no
if [ -e /run/reboot-required ] || [ -e /var/run/reboot-required ]; then RR=yes; fi
RUN=$(uname -r); LAT=$(ls -1 /boot/vmlinuz-* 2>/dev/null | sed "s|.*/vmlinuz-||" | sort -V | tail -1)
if [ -n "$LAT" ] && [ "$LAT" != "$RUN" ]; then RR=yes; fi
echo "REBOOT=$RR"
'''

PRODUCT_NAMES = {
    "pve": "Proxmox VE",
    "pbs": "Proxmox Backup Server",
    "pmg": "Proxmox Mail Gateway",
    "pdm": "Proxmox Datacenter Manager",
}


def build_command(action, username):
    base = ACTIONS[action]
    cmd = f"DEBIAN_FRONTEND=noninteractive {base}"
    if username != "root":
        cmd = "sudo -n " + cmd
    # LC_ALL=C forces English apt output for a consistent console regardless of
    # each machine's system locale (display only — does not change the machine).
    # Locale variables survive sudo via its default env_keep.
    return "LC_ALL=C " + cmd


def _count_command(username):
    cmd = "apt-get -s -o Debug::NoLocking=true dist-upgrade"
    if username != "root":
        cmd = "sudo -n " + cmd
    return "LC_ALL=C " + cmd


def _ver_after_slash(s):
    parts = (s or "").split("/")
    return parts[1].strip() if len(parts) > 1 else (s or "").strip()


def parse_detect(out):
    base = ""
    typ = "base"
    ver = ""
    reboot = False
    for line in (out or "").splitlines():
        if line.startswith("BASE="):
            base = line[5:].strip()
        elif line.startswith("TYPE="):
            typ = line[5:].strip()
        elif line.startswith("VER="):
            ver = line[4:].strip()
        elif line.startswith("REBOOT="):
            reboot = line[7:].strip() == "yes"

    if typ in ("pve", "pmg"):
        v = _ver_after_slash(ver)
        os_info = PRODUCT_NAMES[typ] + ((" " + v) if v else "")
        os_type = typ
    elif typ in ("pbs", "pdm"):
        os_info = PRODUCT_NAMES[typ] + ((" " + ver) if ver else "")
        os_type = typ
    else:
        os_info = base or "Unknown OS"
        os_type = "ubuntu" if "ubuntu" in base.lower() else "debian"
    return {"os_info": os_info[:MAX_OS_INFO], "os_type": os_type, "reboot": reboot}


def sequence_for(kind, os_type):
    """Return the ordered action list for a job kind, OS-aware."""
    if kind == "check":
        return ["update"]
    proxmox = os_type in PROXMOX_TYPES
    if kind == "full-update":
        return ["update", "full-upgrade", "autoremove"]
    # kind == "update": Proxmox must use full-upgrade (dist-upgrade)
    return ["update", "full-upgrade" if proxmox else "upgrade", "autoremove"]


def _host_token(host, port):
    return host if port == 22 else f"[{host}]:{port}"


def _host_is_known(host, port):
    if not os.path.exists(KNOWN_HOSTS_PATH):
        return False
    token = _host_token(host, port)
    with open(KNOWN_HOSTS_PATH, encoding="utf-8") as f:
        for line in f:
            if line.strip() and line.split()[0] == token:
                return True
    return False


async def _connect(machine, *, learn=False):
    host, port = machine["host"], machine["port"]
    if learn and not _host_is_known(host, port):
        conn = await asyncio.wait_for(asyncssh.connect(
            host=host, port=port, username=machine["username"],
            client_keys=[SSH_KEY_PATH], known_hosts=None), timeout=CONNECT_TIMEOUT)
        _remember_host_key(host, port, conn)
        return conn
    return await asyncio.wait_for(asyncssh.connect(
        host=host, port=port, username=machine["username"],
        client_keys=[SSH_KEY_PATH], known_hosts=KNOWN_HOSTS_PATH), timeout=CONNECT_TIMEOUT)


def _remember_host_key(host, port, conn):
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


async def _detect(conn):
    try:
        res = await conn.run(DETECT_CMD, check=False)
        return parse_detect(res.stdout or "")
    except Exception:
        return {"os_info": "Unknown OS", "os_type": "unknown", "reboot": False}


async def _count_pending(conn, username):
    try:
        res = await conn.run(_count_command(username), check=False)
        if res.exit_status != 0:
            return None
        return sum(1 for ln in (res.stdout or "").splitlines() if ln.startswith("Inst "))
    except Exception:
        return None


def _is_enterprise_401(line):
    low = line.lower()
    return "enterprise.proxmox.com" in low and ("401" in low or "unauthorized" in low)


async def test_machine(machine):
    """Connectivity + OS detection only (no apt changes)."""
    try:
        async with await _connect(machine, learn=True) as conn:
            det = await _detect(conn)
            if machine["username"] != "root":
                sudo = await conn.run("sudo -n true", check=False)
                if sudo.exit_status != 0:
                    return {"ok": False, "os_info": det["os_info"], "os_type": det["os_type"],
                            "reboot_required": det["reboot"],
                            "error": "passwordless sudo (NOPASSWD) not configured for this user"}
            return {"ok": True, "os_info": det["os_info"], "os_type": det["os_type"],
                    "reboot_required": det["reboot"]}
    except asyncio.TimeoutError:
        return {"ok": False, "error": "Connection timed out"}
    except asyncssh.HostKeyNotVerifiable:
        return {"ok": False, "error": "Host key changed or not verifiable (possible MITM)"}
    except (OSError, asyncssh.Error) as e:
        return {"ok": False, "error": str(e)}


async def run(machine, kind, on_line):
    """Connect once, detect the OS, run the OS-aware sequence for `kind`,
    count pending updates and re-check reboot status.

    Returns dict with: ok, error, failed_action, pending, os_info, os_type,
    reboot_required, enterprise_error.
    """
    r = {"ok": False, "error": None, "failed_action": None, "pending": None,
         "os_info": None, "os_type": None, "reboot_required": None, "enterprise_error": False}
    async with _semaphore:
        try:
            async with await _connect(machine, learn=True) as conn:
                det = await _detect(conn)
                r["os_info"], r["os_type"], r["reboot_required"] = det["os_info"], det["os_type"], det["reboot"]
                actions = sequence_for(kind, det["os_type"])
                ent = {"seen": False}

                for action in actions:
                    cmd = build_command(action, machine["username"])
                    await on_line(f"$ {ACTIONS[action]}")
                    async with conn.create_process(cmd, stderr=asyncssh.STDOUT) as proc:
                        async def _stream():
                            async for line in proc.stdout:
                                ln = line.rstrip("\n")
                                if _is_enterprise_401(ln):
                                    ent["seen"] = True
                                await on_line(ln)
                        try:
                            await asyncio.wait_for(_stream(), timeout=COMMAND_TIMEOUT)
                        except asyncio.TimeoutError:
                            proc.terminate()
                            r["error"] = "Command timed out"
                            r["failed_action"] = action
                            return r
                    if proc.exit_status != 0:
                        r["enterprise_error"] = ent["seen"]
                        if ent["seen"] and action == "update":
                            r["error"] = ("Proxmox enterprise repository needs a subscription (401). "
                                          "Switch to the no-subscription repo or add a subscription key.")
                        else:
                            err = f"Exit code {proc.exit_status}"
                            if proc.exit_status == 1 and machine["username"] != "root":
                                err += " (check sudo NOPASSWD configuration)"
                            r["error"] = err
                        r["failed_action"] = action
                        return r

                r["pending"] = await _count_pending(conn, machine["username"])
                det2 = await _detect(conn)
                r["reboot_required"] = det2["reboot"]
                r["enterprise_error"] = ent["seen"]
                r["ok"] = True
            return r
        except asyncio.TimeoutError:
            r["error"] = "Connection timed out"
            return r
        except asyncssh.HostKeyNotVerifiable:
            r["error"] = "Host key changed or not verifiable (possible MITM)"
            return r
        except (OSError, asyncssh.Error) as e:
            r["error"] = str(e)
            return r


def get_public_key():
    try:
        with open(SSH_KEY_PATH + ".pub", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""
