"""Runs INSIDE the cdl-api container (piped to `python -` over ssh): remove the records of one phone number.

    python - 4656            # dry run: shows what would be deleted, deletes nothing
    python - 4656 --apply    # deletes it, in one transaction (all or nothing)

Matches by the LAST FOUR DIGITS of the applicant's phone or callback phone, or of a call's caller number. Deletes the
matching applicants, their calls (and unlinked calls from that caller number), the sync-queue rows and change history
that point at them. Never touches logins. Refuses a suffix that matches more than MAX_APPLICANTS people or MAX_CALLS calls.
The result lists the names it matched, so a dry run shows who would go.
It does NOT touch Zoho or VAPI: the candidate in Zoho and the call log and recording in VAPI stay until you remove them there.
"""
import os
import re
import sys

import psycopg

MAX_APPLICANTS = 3
MAX_CALLS = 20


def run(conn, last4, apply=False):
    if not re.fullmatch(r"\d{4}", last4 or ""):
        raise ValueError("give exactly the last four digits, e.g. 4656")
    pattern = "%" + last4
    with conn.transaction():
        applicants = [r[0] for r in conn.execute(
            "SELECT id FROM applicants WHERE phone_e164 LIKE %s OR callback_phone LIKE %s", (pattern, pattern))]
        if len(applicants) > MAX_APPLICANTS:
            raise ValueError(f"{len(applicants)} applicants end in {last4}; refusing (limit {MAX_APPLICANTS})")
        calls = [r[0] for r in conn.execute(
            "SELECT id FROM calls WHERE applicant_id = ANY(%s) OR caller_number LIKE %s", (applicants, pattern))]
        if len(calls) > MAX_CALLS:
            raise ValueError(f"{len(calls)} calls match {last4}; refusing (limit {MAX_CALLS})")
        names = [r[0] for r in conn.execute("SELECT name FROM applicants WHERE id = ANY(%s) ORDER BY id", (applicants,))]
        outbox = [r[0] for r in conn.execute(
            "SELECT id FROM outbox WHERE call_id = ANY(%s) OR applicant_id = ANY(%s)", (calls, applicants))]
        audit = [r[0] for r in conn.execute(
            "SELECT id FROM audit_log WHERE call_id = ANY(%s) OR applicant_id = ANY(%s)", (calls, applicants))]
        if apply:  # children first, so the foreign keys never block a delete
            conn.execute("DELETE FROM outbox WHERE id = ANY(%s)", (outbox,))
            conn.execute("DELETE FROM audit_log WHERE id = ANY(%s)", (audit,))
            conn.execute("DELETE FROM calls WHERE id = ANY(%s)", (calls,))
            conn.execute("DELETE FROM applicants WHERE id = ANY(%s)", (applicants,))
    return {"applicants": len(applicants), "calls": len(calls), "outbox": len(outbox), "audit_log": len(audit),
            "applied": apply, "people": names}


def main(argv):
    args = [a for a in argv if a != "--apply"]
    apply = "--apply" in argv
    if len(args) != 1:
        print("usage: python - <last4> [--apply]")
        return 2
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        try:
            result = run(conn, args[0], apply)
        except ValueError as exc:
            print(f"refused: {exc}")
            return 1
    print(("DELETED " if apply else "DRY RUN, nothing deleted. Would delete ") + str(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
