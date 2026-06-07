"""Création du compte administrateur (utilisé par install.sh).

Usage : ADMIN_USERNAME=... ADMIN_PASSWORD=... python -m app.create_admin
(variables d'environnement pour ne pas exposer le mot de passe dans `ps`)
"""
import os
import sys

from . import auth
from .database import init_db


def main():
    username = os.environ.get("ADMIN_USERNAME", "").strip()
    password = os.environ.get("ADMIN_PASSWORD", "")
    if not username or not password:
        print("Erreur : définir ADMIN_USERNAME et ADMIN_PASSWORD", file=sys.stderr)
        sys.exit(1)
    if len(password) < 10:
        print("Erreur : mot de passe trop court (10 caractères minimum)", file=sys.stderr)
        sys.exit(1)

    init_db()
    if auth.get_user_by_name(username):
        print(f"L'utilisateur '{username}' existe déjà, rien à faire.")
        return
    auth.create_user(username, password)
    print(f"Administrateur '{username}' créé. Le MFA sera configuré au premier login.")


if __name__ == "__main__":
    main()
