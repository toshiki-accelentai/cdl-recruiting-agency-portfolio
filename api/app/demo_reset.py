"""Nightly reset of the public demo.

    DEMO_MODE=1 python -m app.demo_reset

Deletes the demo's calls, applicants, outbox rows and change history, then writes the fictional seed again, all in
one transaction (if the re-seed fails, the old data stays). Logins (users) are never touched.

Two guards, so it can never wipe the real database: DEMO_MODE must be exactly "1", and every call must carry the
demo marker and no applicant may have a Zoho id. Real calls have neither, so pointing this at the real database
by mistake deletes nothing.
"""
import logging
import sys

import psycopg

from app import demo_seed
from app.config import database_url
from app.db import connect_with_retry

logger = logging.getLogger(__name__)

# Children first, so the foreign keys never block a delete. Fixed names, never input.
TABLES_TO_EMPTY = ("audit_log", "outbox", "calls", "applicants")


class NotDemoDatabase(Exception):
    """A row looks like real data: probably not the demo database."""


def _require_only_demo_rows(conn: psycopg.Connection) -> None:
    real_calls = conn.execute(
        "SELECT count(*) FROM calls WHERE raw_payload ->> 'demo' IS DISTINCT FROM 'true'").fetchone()[0]
    if real_calls:
        raise NotDemoDatabase(f"{real_calls} call(s) have no demo marker: refusing to delete")
    with_zoho_id = conn.execute(
        "SELECT count(*) FROM applicants WHERE zoho_candidate_id IS NOT NULL").fetchone()[0]
    if with_zoho_id:
        raise NotDemoDatabase(f"{with_zoho_id} applicant(s) have a Zoho id: refusing to delete")


def reset(conn: psycopg.Connection) -> None:
    """Empty the demo tables and re-seed in one transaction. Raises before deleting if a guard fails."""
    demo_seed.require_demo_mode()
    with conn.transaction():
        _require_only_demo_rows(conn)
        for table in TABLES_TO_EMPTY:
            conn.execute(f"DELETE FROM {table}")
        demo_seed.write_demo_rows(conn)


def main() -> int:
    try:
        demo_seed.require_demo_mode()
        with connect_with_retry(database_url()) as conn:
            reset(conn)
    except (demo_seed.NotDemoMode, NotDemoDatabase) as exc:
        print(f"demo_reset: {exc}", file=sys.stderr)
        return 1
    print(f"demo_reset: demo data replaced with {len(demo_seed.PEOPLE)} fictional applicants")
    return 0


if __name__ == "__main__":
    sys.exit(main())
