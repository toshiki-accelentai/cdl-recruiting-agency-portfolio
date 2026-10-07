#!/usr/bin/env python3
"""Read-only Supabase connection check. Never prints the connection string or password.

Reads DATABASE_URL from api/deploy/.env.supabase. Any error is reported by type only, because
library messages can echo the URL (and its password).

    api\.venv\Scripts\python.exe scripts\check_supabase_connection.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import psycopg

FILE = Path(__file__).resolve().parent.parent / "api" / "deploy" / ".env.supabase"


def main() -> None:
    raw = FILE.read_text(encoding="utf-8-sig").strip()
    if not raw.startswith("DATABASE_URL="):
        sys.exit("file must start with DATABASE_URL=")
    url = raw.split("=", 1)[1].strip().strip('"').strip("'")
    # Shape checks that never echo the value:
    match = re.fullmatch(r"postgres(?:ql)?://([^:/@\[\]]+):([^\[\]]+)@([^@/:\[\]]+):(\d+)/(\w+)", url)
    print("has square brackets:", "[" in url or "]" in url)
    print("more than one @ sign (password has a symbol or the URL is malformed):", url.count("@") > 1)
    if not match:
        sys.exit("URL shape is wrong (check: no [ ], password has no symbols, ends with :5432/postgres)")
    user, _password, host, port, db = match.groups()
    print(f"shape ok | user prefix: {user.split('.')[0]} | user has .projectref: {'.' in user} | "
          f"password length: {len(_password)} | alphanumeric only: {_password.isalnum()} | host: {host} | port: {port} | db: {db}")
    if port != "5432":
        print("WARNING: use the Session pooler on port 5432, not 6543")
    try:
        with psycopg.connect(url, connect_timeout=15) as conn:
            version = conn.execute("select version()").fetchone()[0][:40]
            tables = [r[0] for r in conn.execute("select tablename from pg_tables where schemaname = 'public'")]
        print("connected:", version, "| tables in public:", tables)
    except Exception as exc:  # libpq messages never contain the password, but redact it anyway
        detail = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
        for secret in (_password, url):
            detail = detail.replace(secret, "***")
        sys.exit(f"CONNECT FAILED: {type(exc).__name__}: {detail[:200]}")


if __name__ == "__main__":
    main()
