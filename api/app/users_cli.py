"""Create, list and rotate dashboard logins from the command line.

    python -m app.users_cli create demo recruiter --write-password-to demo.password
    python -m app.users_cli create owner admin --password-file my-chosen-password.txt
    python -m app.users_cli rotate demo --write-password-to demo.new.password
    python -m app.users_cli list
    (add --env-file path/to/file.env to read DATABASE_URL from a file instead of the environment)

A password is NEVER printed. It is generated into a file only its owner can read, or read from a file you
provide, so it cannot end up in a chat, a log, shell history or git. Rotating bumps session_version, which
logs everyone out.
"""
import argparse
import os
import secrets
import sys
from pathlib import Path

from app.auth import change_password, create_user
from app.config import database_url
from app.db import connect_with_retry

MIN_PASSWORD_LENGTH = 12
GENERATED_PASSWORD_BYTES = 18  # token_urlsafe(18) is 24 characters
ROLES = ("recruiter", "admin")


class CliError(Exception):
    """A problem to report to the person at the keyboard, without a traceback."""


def load_database_url(env_file: str) -> None:
    path = Path(env_file)
    if not path.is_file():
        raise CliError(f"env file not found: {env_file}")
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.strip().startswith("DATABASE_URL="):
            os.environ["DATABASE_URL"] = line.split("=", 1)[1].strip().strip('"').strip("'")
            return
    raise CliError(f"env file has no DATABASE_URL: {env_file}")


def password_from_file(path: str) -> str:
    try:
        password = Path(path).read_text(encoding="utf-8").rstrip("\r\n")
    except OSError:
        raise CliError(f"cannot read the password file: {path}")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise CliError(f"the password must be at least {MIN_PASSWORD_LENGTH} characters")
    return password


def write_new_secret_file(path: str, secret: str) -> None:
    """Owner-only, and never over an existing file (that could be someone's only copy of a password)."""
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise CliError(f"password file already exists, not overwriting: {path}")
    except OSError:
        raise CliError(f"cannot write the password file: {path}")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(secret + "\n")


def choose_password(args) -> tuple[str, bool]:
    """(password, generated). Checks only; nothing is written yet."""
    if args.password_file:
        return password_from_file(args.password_file), False
    if args.write_password_to:
        return secrets.token_urlsafe(GENERATED_PASSWORD_BYTES), True
    raise CliError("give --password-file (use your own password) or --write-password-to (generate one)")


def user_exists(conn, username: str) -> bool:
    return conn.execute("SELECT 1 FROM users WHERE username = %s", (username,)).fetchone() is not None


def run_create(args) -> None:
    password, generated = choose_password(args)
    with connect_with_retry(database_url()) as conn:
        if user_exists(conn, args.username):
            raise CliError(f"user already exists: {args.username}")
        if generated:
            write_new_secret_file(args.write_password_to, password)  # before the insert, so it cannot be lost
        try:
            with conn.transaction():
                create_user(conn, args.username, password, args.role)
        except Exception:
            if generated:
                Path(args.write_password_to).unlink(missing_ok=True)
            raise
    source = args.write_password_to if generated else args.password_file
    print(f"created {args.username} ({args.role}). Password {'saved to' if generated else 'read from'}: {source}")


def run_rotate(args) -> None:
    password, generated = choose_password(args)
    with connect_with_retry(database_url()) as conn:
        if not user_exists(conn, args.username):
            raise CliError(f"no such user: {args.username}")
        if generated:
            write_new_secret_file(args.write_password_to, password)
        try:
            with conn.transaction():
                change_password(conn, args.username, password)
        except Exception:
            if generated:
                Path(args.write_password_to).unlink(missing_ok=True)
            raise
    source = args.write_password_to if generated else args.password_file
    print(f"rotated {args.username}. New password {'saved to' if generated else 'read from'}: {source}. Everyone was logged out.")


def run_list(args) -> None:
    with connect_with_retry(database_url()) as conn:
        found = conn.execute("SELECT username, role, created_at::date FROM users ORDER BY username").fetchall()
    if not found:
        print("no users yet")
    for username, role, created in found:
        print(f"{username}  {role}  created {created}")


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--env-file", help="read DATABASE_URL from this file instead of the environment")
    password_options = argparse.ArgumentParser(add_help=False)
    password_options.add_argument("--password-file", help="use the password in this file (at least 12 characters)")
    password_options.add_argument("--write-password-to", help="generate a password and save it to this new file (owner-only)")

    parser = argparse.ArgumentParser(prog="python -m app.users_cli", description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", parents=[common, password_options], help="add a login")
    create.add_argument("username")
    create.add_argument("role", choices=ROLES)
    create.set_defaults(run=run_create)
    rotate = commands.add_parser("rotate", parents=[common, password_options], help="change a password and log everyone out")
    rotate.add_argument("username")
    rotate.set_defaults(run=run_rotate)
    listing = commands.add_parser("list", parents=[common], help="show usernames and roles")
    listing.set_defaults(run=run_list)
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.env_file:
            load_database_url(args.env_file)
        args.run(args)
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
