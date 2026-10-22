"""Fictional data for the public demo server.

    DEMO_MODE=1 python -m app.demo_seed

Two guards, so it can never write into the real database: DEMO_MODE must be exactly "1", and the database must be
empty (no applicants, calls, outbox rows or change history). Every name, number and city is made up; phone numbers
use 555-0100 to 555-0199, which US numbering keeps for fiction. Times are relative to now, so the demo always looks
like this week. No recordings yet (step 2b) and no Zoho ids (the demo never talks to Zoho).
The 8 featured people below are hand-written; the rest of the roster is the table in demo_roster.py.
"""
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

import psycopg
from psycopg.types.json import Jsonb

from app.config import database_url
from app import demo_roster
from app.db import connect_with_retry

logger = logging.getLogger(__name__)


class NotDemoMode(Exception):
    """DEMO_MODE is not set to exactly "1"."""


class DatabaseNotEmpty(Exception):
    """The database already holds data: probably not the demo database."""


DEMO_PAYLOAD = Jsonb({"demo": True})  # stands in for VAPI's raw request, which the demo never has
TABLES_THAT_MUST_BE_EMPTY = ("applicants", "calls", "outbox", "audit_log")


def _call(hours_ago, summary, lines, sync=None, callback_in_hours=None):
    return {"hours_ago": hours_ago, "summary": summary, "lines": lines, "sync": sync,
            "callback_in_hours": callback_in_hours}


def _person(name, phone, city, state, zip_code, experience, readiness, temperature, calls,
            follow_up="to_call", note="", follow_up_hours_ago=None, callback_phone=""):
    return {"name": name, "phone": phone, "callback_phone": callback_phone, "city": city, "state": state,
            "zip": zip_code, "experience": experience, "readiness": readiness, "temperature": temperature,
            "calls": calls, "follow_up": follow_up, "note": note, "follow_up_hours_ago": follow_up_hours_ago}


def _intake(name, city, experience, readiness, callback):
    """A short, typical intake conversation."""
    return [("agent", "Thanks for calling Frontline CDL Staffing. Are you a CDL driver looking for work?"),
            ("driver", "Yes, I'm looking for a new position."),
            ("agent", "Great. Can I get your full name?"),
            ("driver", name),
            ("agent", "And where are you based?"),
            ("driver", city),
            ("agent", "How much driving experience do you have?"),
            ("driver", experience),
            ("agent", "When could you start?"),
            ("driver", readiness),
            ("agent", "When is a good time for a recruiter to call you back?"),
            ("driver", callback),
            ("agent", "Perfect, a recruiter will call you then. Drive safe.")]


SENT = {"status": "sent"}
WAITING = {"status": "pending", "attempts": 2, "last_error": "zoho unreachable: timed out", "retry_in_minutes": 8}
FAILED = {"status": "failed", "attempts": 6, "last_error": "zoho 400: INVALID_DATA (Zip_Code)"}

PEOPLE = [
    _person("Marcus Bell", "+12065550142", "Seattle", "WA", "98108", "6 years, OTR", "tomorrow", "HOT",
            [_call(2, "Six-year OTR driver in Seattle, can start tomorrow, wants regional runs.",
                   _intake("Marcus Bell", "Seattle, Washington", "Six years over the road", "Tomorrow",
                           "This afternoon"), SENT, callback_in_hours=3)]),
    _person("Dana Ortiz", "+16025550117", "Phoenix", "AZ", "85009", "3 years, flatbed", "in 2 days", "HOT",
            [_call(5, "Flatbed driver, three years, ready in two days. Zoho save is still retrying.",
                   _intake("Dana Ortiz", "Phoenix, Arizona", "Three years flatbed", "In two days",
                           "Tomorrow morning"), WAITING, callback_in_hours=18)]),
    _person("Luis Romero", "+12145550163", "Dallas", "TX", "75212", "10 years, tanker", "next week", "MEDIUM",
            [_call(70, "Tanker driver, ten years, Hazmat. Asked about home-time.",
                   _intake("Luis Romero", "Dallas, Texas", "Ten years, tanker with Hazmat", "Next week",
                           "Any weekday after 4"), SENT),
             _call(4, "Called again: wants to confirm the recruiter has his new availability.",
                   [("agent", "Thanks for calling Frontline CDL Staffing."),
                    ("driver", "I called a few days ago. I can start sooner now, maybe Monday."),
                    ("agent", "Got it, I'll pass that on. A recruiter will call you back.")], SENT,
                   callback_in_hours=26)],
            follow_up="called", note="Left details about the Fort Worth tanker route.", follow_up_hours_ago=48),
    _person("Tanya Brooks", "+14045550189", "Atlanta", "GA", "30318", "2 years, local", "in 5 days", "MEDIUM",
            [_call(30, "Local driver, two years, prefers day shifts. Zip code failed Zoho's check.",
                   _intake("Tanya Brooks", "Atlanta, Georgia", "Two years local", "In five days",
                           "Friday at noon"), FAILED, callback_in_hours=40)]),
    _person("Kevin Shaw", "+13125550104", "Chicago", "IL", "60632", "1 year", "in 2 weeks", "WARM",
            [_call(50, "Newer driver, one year, finishing current job first.",
                   _intake("Kevin Shaw", "Chicago, Illinois", "About one year", "In two weeks",
                           "Next Tuesday"), SENT)],
            follow_up="no_answer", note="No answer, voicemail left.", follow_up_hours_ago=20,
            callback_phone="+13125550105"),
    _person("Ray Delgado", "+18135550131", "Tampa", "FL", "33610", "15 years, OTR", "in 10 days", "WARM",
            [_call(96, "Veteran OTR driver, fifteen years, wants a team position.",
                   _intake("Ray Delgado", "Tampa, Florida", "Fifteen years over the road", "In about ten days",
                           "Mornings"), SENT)],
            follow_up="done", note="Placed with the Lakeland team carrier.", follow_up_hours_ago=60),
    _person("Jasmine Cole", "+16155550176", "Nashville", "TN", "37210", "4 years, reefer", "next month", "COLD",
            [_call(120, "Reefer driver, four years, not available until next month.",
                   _intake("Jasmine Cole", "Nashville, Tennessee", "Four years reefer", "Next month",
                           "Any time next week"), SENT)],
            follow_up="called", note="Check in again in three weeks.", follow_up_hours_ago=100),
    _person("Owen Price", "+15035550158", "Portland", "OR", "97217", "8 years, dry van", "in 3 days", "HOT",
            [_call(1, "Dry van driver, eight years, can start in three days.",
                   _intake("Owen Price", "Portland, Oregon", "Eight years dry van", "In three days",
                           "In two hours"), SENT, callback_in_hours=2)]),
]

# Someone who called but never reached the intake questions: kept, flagged, with no applicant.
NO_INTAKE = _call(7, "Caller asked about dispatcher jobs, not a driver. Hung up before the questions.",
                  [("agent", "Thanks for calling Frontline CDL Staffing. Are you a CDL driver looking for work?"),
                   ("driver", "No, I'm asking about dispatcher openings."),
                   ("agent", "This line is for drivers, but I can note your call for the team.")])
NO_INTAKE_CALLER = "+12535550199"

SYNC_BY_KEY = {demo_roster.SENT: SENT, demo_roster.WAITING: WAITING, demo_roster.FAILED: FAILED}


def _roster_person(index, row):
    (name, phone, city, state, zip_code, years, equipment, ready, temperature, hours_ago, callback_in,
     follow_up, note, sync_key, earlier_hours) = row
    first = name.split()[0]
    sync = SYNC_BY_KEY[sync_key]
    latest = _call(hours_ago, f"{first} has {years} of {equipment} driving, based in {city}, {state}. Ready to start {ready}.",
                   _intake(name, f"{city}, {demo_roster.STATE_NAMES[state]}", f"{years} of {equipment}", ready.capitalize(),
                           demo_roster.CALLBACK_WORDS[index % len(demo_roster.CALLBACK_WORDS)]),
                   sync, callback_in_hours=callback_in)
    calls = [latest]
    if earlier_hours:
        calls.insert(0, _call(earlier_hours, f"{first} called to ask about {equipment} work near {city}.",
                              _intake(name, f"{city}, {demo_roster.STATE_NAMES[state]}", f"{years} of {equipment}", "Not sure yet",
                                      "Any weekday afternoon"), SENT))
        latest["summary"] = f"{first} called again with an update: ready to start {ready}."
        latest["lines"] = [("agent", "Thanks for calling Frontline CDL Staffing."),
                           ("driver", f"I called earlier this week. I can start {ready} now."),
                           ("agent", "Got it, I'll pass that on. A recruiter will call you back.")]
    return _person(name, phone, city, state, zip_code, f"{years}, {equipment}", ready, temperature, calls,
                   follow_up=follow_up, note=note,
                   follow_up_hours_ago=None if follow_up == "to_call" else max(1, hours_ago - 10))


PEOPLE += [_roster_person(i, row) for i, row in enumerate(demo_roster.ROSTER)]
EXTRA_UNSAVED = [(_call(hours, summary, lines) | {"reason": reason}, caller)
                 for hours, caller, reason, summary, lines in demo_roster.UNSAVED_CALLS]


def require_demo_mode() -> None:
    if os.environ.get("DEMO_MODE") != "1":
        raise NotDemoMode("DEMO_MODE=1 is required: this writes fictional data")


def _require_empty(conn: psycopg.Connection) -> None:
    for table in TABLES_THAT_MUST_BE_EMPTY:  # fixed names, never input
        if conn.execute(f"SELECT EXISTS (SELECT 1 FROM {table})").fetchone()[0]:
            raise DatabaseNotEmpty(f"{table} already has rows: refusing to seed")


def _transcript(lines) -> Jsonb:
    return Jsonb([{"speaker": speaker, "text": text, "start": round(index * 4.5, 1)}
                  for index, (speaker, text) in enumerate(lines)])


def _insert_call(conn, now, number, applicant_id, call, caller) -> int:
    created = now - timedelta(hours=call["hours_ago"])
    callback = None if call["callback_in_hours"] is None else now + timedelta(hours=call["callback_in_hours"])
    return conn.execute(
        "INSERT INTO calls (vapi_call_id, applicant_id, preferred_callback_at, raw_payload, needs_review, "
        "review_reason, summary, transcript, report_received_at, caller_number, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (f"demo-call-{number}", applicant_id, callback, DEMO_PAYLOAD, applicant_id is None,
         None if applicant_id else call.get("reason", "no_intake"), call["summary"], _transcript(call["lines"]),
         created + timedelta(minutes=2), caller, created)).fetchone()[0]


def _insert_sync(conn, now, call_id, applicant_id, sync) -> None:
    sent_at = now if sync["status"] == "sent" else None
    next_at = now + timedelta(minutes=sync.get("retry_in_minutes", 0))
    conn.execute(
        "INSERT INTO outbox (call_id, applicant_id, status, attempts, next_attempt_at, last_error, sent_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (call_id, applicant_id, sync["status"], sync.get("attempts", 1), next_at, sync.get("last_error"), sent_at))


def _insert_person(conn, now, person, numbers) -> None:
    follow_up_at = (None if person["follow_up_hours_ago"] is None
                    else now - timedelta(hours=person["follow_up_hours_ago"]))
    applicant_id = conn.execute(
        "INSERT INTO applicants (name, phone_e164, callback_phone, city, state, zip_code, experience, readiness, "
        "temperature, follow_up_status, follow_up_note, follow_up_updated_at, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (person["name"], person["phone"], person["callback_phone"], person["city"], person["state"], person["zip"],
         person["experience"], person["readiness"], person["temperature"], person["follow_up"], person["note"],
         follow_up_at, now - timedelta(hours=max(c["hours_ago"] for c in person["calls"])))).fetchone()[0]
    for call in person["calls"]:
        call_id = _insert_call(conn, now, next(numbers), applicant_id, call, person["phone"])
        _insert_sync(conn, now, call_id, applicant_id, call["sync"])


def write_demo_rows(conn: psycopg.Connection, now: datetime | None = None) -> None:
    """Insert the fictional rows. No guards here: the callers (seed, demo_reset) check them first."""
    now = now or datetime.now(timezone.utc)
    numbers = iter(range(1, 1000))
    for person in PEOPLE:
        _insert_person(conn, now, person, numbers)
    _insert_call(conn, now, next(numbers), None, NO_INTAKE, NO_INTAKE_CALLER)
    for call, caller in EXTRA_UNSAVED:
        _insert_call(conn, now, next(numbers), None, call, caller)


def seed(conn: psycopg.Connection, now: datetime | None = None) -> None:
    """Write the fictional demo data in one transaction. Raises before writing if a guard fails."""
    require_demo_mode()
    with conn.transaction():
        _require_empty(conn)
        write_demo_rows(conn, now)


def main() -> int:
    try:
        require_demo_mode()
        with connect_with_retry(database_url()) as conn:
            seed(conn)
    except (NotDemoMode, DatabaseNotEmpty) as exc:
        print(f"demo_seed: {exc}", file=sys.stderr)
        return 1
    print(f"demo_seed: wrote {len(PEOPLE)} fictional applicants")
    return 0


if __name__ == "__main__":
    sys.exit(main())
