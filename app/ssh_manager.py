"""PatchPilot - Exécution SSH.

Seules 3 commandes sont autorisées (liste blanche stricte) :
  - apt-get update
  - apt-get upgrade -y
  - apt-get full-upgrade -y
Aucune autre commande ne peut être envoyée aux machines.
"""
import asyncio

import asyncssh

from .database import SSH_KEY_PATH

# Liste blanche STRICTE — ne jamais construire de commande à partir d'une saisie utilisateur.
ACTIONS = {
    "update": "apt-get update",
    "upgrade": "apt-get upgrade -y",
    "full-upgrade": "apt-get full-upgrade -y",
}

CONNECT_TIMEOUT = 15
COMMAND_TIMEOUT = 3600  # 1 h max par commande

# Limite de connexions SSH simultanées pour "tout mettre à jour"
MAX_PARALLEL = 10
_semaphore = asyncio.Semaphore(MAX_PARALLEL)


def build_command(action: str, username: str) -> str:
    base = ACTIONS[action]  # KeyError si action hors liste blanche => rejet
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
            known_hosts=None,  # parc interne ; voir README pour durcir
        ),
        timeout=CONNECT_TIMEOUT,
    )


async def test_machine(machine) -> dict:
    """Teste la connexion, détecte l'OS et vérifie les droits (root ou sudo -n)."""
    try:
        async with await _connect(machine) as conn:
            res = await conn.run(". /etc/os-release && echo \"$PRETTY_NAME\"", check=False)
            os_info = (res.stdout or "").strip() or "OS inconnu"

            if machine["username"] != "root":
                sudo = await conn.run("sudo -n true", check=False)
                if sudo.exit_status != 0:
                    return {
                        "ok": False, "os_info": os_info,
                        "error": "sudo sans mot de passe (NOPASSWD) non configuré pour cet utilisateur",
                    }
            return {"ok": True, "os_info": os_info}
    except asyncio.TimeoutError:
        return {"ok": False, "error": "Délai de connexion dépassé"}
    except (OSError, asyncssh.Error) as e:
        return {"ok": False, "error": str(e)}


async def run_action(machine, action: str, on_line) -> dict:
    """Exécute une action whitelistée et streame chaque ligne via on_line(str).

    Retourne {"ok": bool, "exit_status": int | None, "error": str | None}.
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
                        return {"ok": False, "exit_status": None, "error": "Délai d'exécution dépassé"}
                exit_status = proc.exit_status
                if exit_status == 0:
                    return {"ok": True, "exit_status": 0, "error": None}
                err = f"Code de sortie {exit_status}"
                if exit_status == 1 and machine["username"] != "root":
                    err += " (vérifier la configuration sudo NOPASSWD)"
                return {"ok": False, "exit_status": exit_status, "error": err}
        except asyncio.TimeoutError:
            return {"ok": False, "exit_status": None, "error": "Délai de connexion dépassé"}
        except (OSError, asyncssh.Error) as e:
            return {"ok": False, "exit_status": None, "error": str(e)}


def get_public_key() -> str:
    try:
        with open(SSH_KEY_PATH + ".pub", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return ""
