"""Create the administrator account (used by install.sh).

Usage: ADMIN_USERNAME=... ADMIN_PASSWORD=... python -m app.create_admin
(environment variables so the password never shows up in `ps`)
"""
import os
import sys

from . import auth
from .database import init_db


def main():
    username = os.environ.get("ADMIN_USERNAME", "").strip()
    password = os.environ.get("ADMIN_PASSWORD", "")
    if not username or not password:
        print("Error: ADMIN_USERNAME and ADMIN_PASSWORD must be set", file=sys.stderr)
        sys.exit(1)
    if len(password) < 10:
        print("Error: password too short (10 characters minimum)", file=sys.stderr)
        sys.exit(1)

    init_db()
    if auth.get_user_by_name(username):
        print(f"User '{username}' already exists, nothing to do.")
        return
    auth.create_user(username, password)
    print(f"Administrator '{username}' created. MFA will be set up on first login.")


if __name__ == "__main__":
    main()
