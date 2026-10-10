"""Outbox worker: sends pending outbox rows to Zoho Recruit.

The database already holds every call, so nothing is lost while Zoho is down. This loop just keeps
trying. Delivery is at-least-once: the candidate upsert is idempotent (matched by phone); in the
rare case Zoho accepts a note and the worker crashes before recording it, that note is sent twice.

Failure handling (see app/zoho.py):  "retry" -> stay pending, wait longer;  "fail" -> mark failed.
Run:  python -m app.worker
"""
from __future__ import annotations

import logging
import os
import time
from zoneinfo import ZoneInfo

import psycopg

from app.config import database_url
from app.logs import setup_logging, short
from app.zoho import ZohoClient, ZohoError, candidate_fields

logger = logging.getLogger(__name__)

MAX_BACKOFF_SECONDS = 900  # keep retrying forever, but never wait more than 15 minutes
POLL_SECONDS = 5

CLAIM_ONE = """
SELECT o.id, o.attempts, a.id, a.name, a.phone_e164, a.city, a.state, a.zip_code, a.experience,
       a.readiness, a.temperature, c.vapi_call_id, c.preferred_callback_at
FROM outbox o
JOIN calls c ON c.id = o.call_id
JOIN applicants a ON a.id = o.applicant_id
WHERE o.status = 'pending' AND o.next_attempt_at <= now()
ORDER BY o.next_attempt_at, o.id
FOR UPDATE OF o SKIP LOCKED
LIMIT 1
"""


def backoff_seconds(attempts: int) -> int:
    """Wait after the Nth failed attempt: 30s, 60s, 120s ... capped at 15 minutes."""
    return min(30 * 2 ** (attempts - 1), MAX_BACKOFF_SECONDS)


def note_content(a: dict, call_id: str, callback) -> str:
    when = callback.astimezone(ZoneInfo("America/Vancouver")).isoformat() if callback else "none"
    return "\n".join([
        f"VAPI Call ID: {call_id}",
        f"Phone: {a['phone_e164']}",
        f"Location: {a['city']}, {a['state']} {a['zip_code']}",
        f"Experience: {a['experience']}",
        f"Readiness: {a['readiness']}",
        f"Temperature: {a['temperature']}",
        f"Requested callback: {when}",
    ])


def process_one(conn: psycopg.Connection, zoho) -> str | None:
    """Claim one due row, send it, record the outcome. Returns sent / retry / failed / None.

    The log line is written only after the transaction has committed, so the log never says
    "sent" for a row the database did not really record as sent.
    """
    outcome = _claim_and_send(conn, zoho)
    if outcome is None:
        return None
    result, outbox_id, attempt, wait, error = outcome
    if result == "sent":
        logger.info("outbox id=%s sent attempt=%s", outbox_id, attempt)
    elif result == "retry":
        logger.warning("outbox id=%s retry attempt=%s next_in=%ss error=%s",
                       outbox_id, attempt, wait, short(error))
    else:
        logger.error("outbox id=%s failed attempt=%s error=%s", outbox_id, attempt, short(error))
    return result


def _claim_and_send(conn: psycopg.Connection, zoho):
    """The database work of process_one. Returns None or (result, outbox_id, attempt, wait, error)."""
    with conn.transaction():  # the row stays locked (other workers skip it) until we finish
        row = conn.execute(CLAIM_ONE).fetchone()
        if row is None:
            return None
        (outbox_id, attempts, applicant_id, name, phone, city, state, zip_code, experience,
         readiness, temperature, call_id, callback) = row
        applicant = {"name": name, "phone_e164": phone, "city": city, "state": state,
                     "zip_code": zip_code, "experience": experience, "readiness": readiness,
                     "temperature": temperature}
        try:
            candidate_id = zoho.upsert_candidate(phone, candidate_fields(applicant))
            zoho.add_note(candidate_id, f"VAPI Intake — {call_id}",
                          note_content(applicant, call_id, callback))
        except ZohoError as exc:
            kind, error = exc.kind, str(exc)
        except Exception as exc:  # a bug on our side must never lose or give up on a lead
            kind, error = "retry", f"unexpected {type(exc).__name__}: {exc}"
        else:
            conn.execute("UPDATE applicants SET zoho_candidate_id = %s WHERE id = %s",
                         (candidate_id, applicant_id))
            conn.execute("UPDATE outbox SET status = 'sent', attempts = attempts + 1, "
                         "sent_at = now(), last_error = NULL WHERE id = %s", (outbox_id,))
            return "sent", outbox_id, attempts + 1, None, None
        if kind == "fail":
            conn.execute("UPDATE outbox SET status = 'failed', attempts = attempts + 1, "
                         "last_error = %s WHERE id = %s", (error, outbox_id))
            return "failed", outbox_id, attempts + 1, None, error
        conn.execute("UPDATE outbox SET attempts = attempts + 1, last_error = %s, "
                     "next_attempt_at = now() + make_interval(secs => %s) WHERE id = %s",
                     (error, backoff_seconds(attempts + 1), outbox_id))
        return "retry", outbox_id, attempts + 1, backoff_seconds(attempts + 1), error


def zoho_from_env() -> ZohoClient:
    env = os.environ
    missing = [k for k in ("ZOHO_CLIENT_ID", "ZOHO_CLIENT_SECRET", "ZOHO_REFRESH_TOKEN") if not env.get(k)]
    if missing:
        raise SystemExit(f"missing environment variables: {', '.join(missing)}")
    return ZohoClient(
        env["ZOHO_CLIENT_ID"], env["ZOHO_CLIENT_SECRET"], env["ZOHO_REFRESH_TOKEN"],
        accounts_domain=env.get("ZOHO_ACCOUNTS_DOMAIN", "https://accounts.zoho.com"),
        api_base=env.get("ZOHO_RECRUIT_API_DOMAIN", "https://recruit.zoho.com").rstrip("/") + "/recruit/v2")


def run_forever(zoho=None, poll_seconds: float = POLL_SECONDS) -> None:
    zoho = zoho or zoho_from_env()
    setup_logging()
    logger.info("outbox worker started")
    while True:
        try:
            with psycopg.connect(database_url()) as conn:
                while process_one(conn, zoho) is not None:
                    pass
        except psycopg.OperationalError as exc:  # database briefly unreachable: just try again
            logger.warning("database unavailable: %s", short(exc))
        time.sleep(poll_seconds)


if __name__ == "__main__":
    run_forever()
