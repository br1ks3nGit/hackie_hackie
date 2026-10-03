"""Create dashboard users or change their password in Postgres (no hashes to copy around).

Usage (from backend/, with DATABASE_URL pointing at the database):
    uv run python scripts/manage_users.py create admin               # prompts for the password
    uv run python scripts/manage_users.py create admin --generate    # random password, printed once
    uv run python scripts/manage_users.py set-password admin
    echo -n 'secret' | uv run python scripts/manage_users.py create admin   # reads stdin

In docker compose: docker compose exec api python scripts/manage_users.py create admin
The first user has to be created here; after that, manage users on the dashboard Users screen.
"""

import argparse
import getpass
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal
from app.services import users
from app.services.users import MIN_PASSWORD_LEN


def _read_password(generate: bool) -> str:
    if generate:
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
    if len(password) < MIN_PASSWORD_LEN:
        sys.stderr.write(
            f"Warning: shorter than {MIN_PASSWORD_LEN} characters; fine for local dev only.\n"
        )
    return password


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (("create", "create a user"), ("set-password", "change a password")):
        cmd = sub.add_parser(name, help=help_text)
        cmd.add_argument("username")
        cmd.add_argument("--generate", action="store_true", help="use a random password")
    args = parser.parse_args()

    with SessionLocal() as db:
        try:
            if args.command == "create":
                user = users.create_user(db, args.username, _read_password(args.generate))
                sys.stdout.write(f"Created user '{user.username}'.\n")
            else:
                user = users.get_by_username(db, args.username.strip())
                if user is None:
                    sys.exit(f"No such user: {args.username}")
                users.set_password(db, user, _read_password(args.generate))
                sys.stdout.write(f"Password changed for '{user.username}'.\n")
        except ValueError as exc:
            sys.exit(str(exc))


if __name__ == "__main__":
    main()
