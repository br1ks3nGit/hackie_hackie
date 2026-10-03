"""Print the DASHBOARD_PASSWORD_HASH line for the insurer dashboard.

Usage (from backend/):
    uv run python scripts/hash_password.py            # prompts for a password
    uv run python scripts/hash_password.py --generate # random password, prints both
    echo -n 'secret' | uv run python scripts/hash_password.py   # reads stdin
"""

import argparse
import getpass
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.passwords import hash_password


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generate", action="store_true", help="create a random password")
    args = parser.parse_args()

    if args.generate:
        password = secrets.token_urlsafe(16)
        sys.stdout.write(f"Password: {password}\n")
    elif sys.stdin.isatty():
        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Repeat: "):
            sys.exit("Passwords do not match.")
    else:
        password = sys.stdin.read().rstrip("\r\n")
    if not password:
        sys.exit("Password must not be empty.")
    sys.stdout.write(f"DASHBOARD_PASSWORD_HASH={hash_password(password)}\n")


if __name__ == "__main__":
    main()
