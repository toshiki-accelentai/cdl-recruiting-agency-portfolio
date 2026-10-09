#!/usr/bin/env python3
"""READ-ONLY status board for the "CRM is down" drill (B2). Writes nothing anywhere.

Shows, per recent call: the outbox state (pending / sent / failed), how many delivery attempts,
when the next one is due, the last error, and the Zoho candidate the worker recorded. With
--zoho it also asks Zoho (one GET search per applicant) whether that candidate really exists.

Reads DATABASE_URL from api/deploy/.env.supabase and, for --zoho, ZOHO_* from the repo-root .env.
Prints no secrets: phones are masked to the last 4 digits, errors are cut to 70 characters.

    api\\.venv\\Scripts\\python.exe scripts\\outbox_status.py [--limit 10] [--zoho]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))
sys.path.insert(0, str(ROOT / "scripts"))

ENV_FILE = ROOT / "api" / "deploy" / ".env.supabase"

QUERY = """
SELECT c.id, a.name, a.phone_e164, o.status, o.attempts,
       EXTRACT(EPOCH FROM (o.next_attempt_at - now()))::int AS due_in_s,
       o.last_error, a.zoho_candidate_id
FROM calls c
LEFT JOIN applicants a ON a.id = c.applicant_id
LEFT JOIN outbox o ON o.call_id = c.id
ORDER BY c.id DESC
LIMIT %s
"""


def database_url() -> str:
    raw = ENV_FILE.read_text(encoding="utf-8-sig").strip()
    if not raw.startswith("DATABASE_URL="):
        sys.exit("api/deploy/.env.supabase must start with DATABASE_URL=")
    return raw.split("=", 1)[1].strip().strip('"').strip("'")


def mask(phone: str | None) -> str:
    return f"…{phone[-4:]}" if phone else "-"


def due_text(status: str | None, due_in_s: int | None) -> str:
    if status != "pending" or due_in_s is None:
        return "-"
    return "now" if due_in_s <= 0 else f"in {due_in_s}s"


def zoho_check(client, phone: str | None, recorded_id: str | None) -> str:
    if not phone:
        return "-"
    try:
        found = client.find_candidate_id(phone)
    except Exception as exc:  # report the kind only; never echo a message that could carry a secret
        return f"lookup failed ({type(exc).__name__})"
    if found is None:
        return "NOT IN ZOHO"
    return "in Zoho" if found == recorded_id else "in Zoho (id differs from DB)"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--zoho", action="store_true", help="also check each applicant in Zoho (read-only)")
    args = parser.parse_args()

    client = None
    if args.zoho:
        from deploy_n8n_workflow import load_env
        os.environ.update({k: v for k, v in load_env().items() if k.startswith("ZOHO_")})
        from app.worker import zoho_from_env
        client = zoho_from_env()

    with psycopg.connect(database_url(), connect_timeout=15) as conn:
        rows = conn.execute(QUERY, (args.limit,)).fetchall()
        counts = dict(conn.execute("SELECT status, count(*) FROM outbox GROUP BY status").fetchall())
        total_calls = conn.execute("SELECT count(*) FROM calls").fetchone()[0]

    print(f"calls in DB: {total_calls} | outbox: " +
          ", ".join(f"{s}={counts.get(s, 0)}" for s in ("pending", "sent", "failed")))
    header = f"{'call':>5} {'driver':<22} {'phone':<8} {'outbox':<8} {'tries':>5} {'next':<9} {'zoho id':<9}"
    print(header + (" zoho check" if client else "") + "  last error")
    for call_id, name, phone, status, attempts, due, error, zoho_id in rows:
        line = (f"{call_id:>5} {(name or '-')[:22]:<22} {mask(phone):<8} {(status or 'NO OUTBOX'):<8} "
                f"{attempts if attempts is not None else '-':>5} {due_text(status, due):<9} "
                f"{('…' + zoho_id[-6:]) if zoho_id else '-':<9}")
        if client:
            line += f" {zoho_check(client, phone, zoho_id):<14}"
        print(line + (f"  {error[:70]}" if error else ""))


if __name__ == "__main__":
    main()
