"""Hang-ups and unknown callers stay out of "Needs a closer look". Written before the code.

Owner decision 2026-10-28: a call that ended before the agent saved details is still kept, but
- from a KNOWN number (it matches an applicant): it is linked to that person and stays in the list, by name
  (for example a cancel request, which never runs the save tool);
- from an unknown number, or no number: it leaves the list and shows up only as a quiet "hang-up".
"""
from pathlib import Path

import psycopg

from tests.conftest import TEST_URL
from tests.test_call_reports import call_row, report
from tests.test_calls_api import add_call, admin_web, web  # noqa: F401  (pytest fixtures)
from tests.test_todo import attention_ids, set_callback_at, sql

KNOWN = "+14155550123"  # the caller number in report()
MIGRATION = Path(__file__).resolve().parents[1] / "migrations" / "013_link_hang_ups.sql"


def hang_up(client, vapi_id, number=KNOWN):
    body = report(call_id=vapi_id)
    body["message"]["call"]["customer"] = {"number": number} if number else None
    assert client.post("/call-reports", json=body).status_code == 201
    return sql("SELECT id FROM calls WHERE vapi_call_id = %s", (vapi_id,))[0][0]


# --- linking at report time -------------------------------------------------------------------

def test_a_hang_up_from_a_known_number_is_linked_to_that_applicant(client, db):
    add_call(name="Carlos Rivera", phone=KNOWN)
    hang_up(client, "cancel-call")
    *_, needs_review, reason, applicant_id = call_row(db, "cancel-call")
    known_id = db.execute("SELECT id FROM applicants WHERE phone_e164 = %s", (KNOWN,)).fetchone()[0]
    assert applicant_id == known_id and needs_review is True and reason == "no_intake"
    assert db.execute("SELECT count(*) FROM outbox").fetchone()[0] == 0  # still nothing to send to Zoho


def test_a_hang_up_from_an_unknown_number_stays_unlinked(client, db):
    add_call(name="Someone Else", phone="+12065550199")
    hang_up(client, "stranger")
    assert call_row(db, "stranger")[-1] is None


def test_a_hang_up_with_no_caller_id_stays_unlinked(client, db):
    add_call(name="Carlos Rivera", phone=KNOWN)
    hang_up(client, "web-call", number=None)
    assert call_row(db, "web-call")[-1] is None


def test_a_known_callers_intake_arriving_after_the_report_still_completes_the_call(client, payload, db):
    """The report can beat the tool call. Linking the placeholder must not turn the intake into a 'replay'."""
    first = client.post("/calls", json=payload).json()
    phone = db.execute("SELECT phone_e164 FROM applicants WHERE id = %s", (first["applicant_id"],)).fetchone()[0]
    payload["message"]["call"]["id"] = "second-call"
    hang_up(client, "second-call", number=phone)
    r = client.post("/calls", json=payload)
    assert r.status_code == 201 and r.json()["duplicate"] is False
    row = db.execute("SELECT needs_review, review_reason, applicant_id FROM calls WHERE vapi_call_id = 'second-call'").fetchone()
    assert row == (False, None, first["applicant_id"])
    assert db.execute("SELECT count(*) FROM outbox").fetchone()[0] == 2  # the second call is queued for Zoho too


# --- the To do page -----------------------------------------------------------------------------

def test_unknown_hang_ups_leave_needs_a_closer_look_but_are_counted(client, web):
    stranger = hang_up(client, "stranger", number="+12065550199")
    no_number = hang_up(client, "web-call", number=None)
    real_problem = add_call(name="Unknown", phone=None, needs_review=True, review_reason="invalid_phone")
    body = web.get("/api/todo").json()
    assert [row["id"] for row in body["attention"]] == [real_problem]
    assert stranger not in [row["id"] for row in body["attention"]] and no_number not in [row["id"] for row in body["attention"]]
    assert body["summary"]["hang_ups_today"] == 2


def test_a_known_callers_hang_up_stays_in_the_list_with_their_name(client, web):
    add_call(name="Carlos Rivera", phone=KNOWN)
    call_id = hang_up(client, "cancel-call")
    row = next(r for r in web.get("/api/todo").json()["attention"] if r["id"] == call_id)
    assert row["applicant"]["name"] == "Carlos Rivera"
    assert web.get("/api/todo").json()["summary"]["hang_ups_today"] == 0


def test_a_later_hang_up_does_not_hide_the_booked_callback_time(client, web):
    booked = add_call(name="Carlos Rivera", phone=KNOWN, minutes_ago=60)
    set_callback_at(booked, 24)
    hang_up(client, "cancel-call")
    row = web.get("/api/todo").json()["call_back"][0]
    assert row["applicant"]["name"] == "Carlos Rivera" and row["preferred_callback_at"] is not None
    assert row["call_count"] == 2


# --- Call activity: the quiet list --------------------------------------------------------------

def test_call_activity_can_list_only_the_hang_ups(client, web):
    add_call(name="Carlos Rivera", phone=KNOWN)
    known = hang_up(client, "cancel-call")
    stranger = hang_up(client, "stranger", number="+12065550199")
    page = web.get("/api/calls?kind=hang_up").json()
    assert [item["id"] for item in page["items"]] == [stranger] and page["total"] == 1
    assert known in [item["id"] for item in web.get("/api/calls").json()["items"]]


def test_an_unknown_kind_is_rejected(web):
    assert web.get("/api/calls?kind=spam").status_code == 422


# --- migration 013: links hang-ups saved before this change -------------------------------------

def test_migration_links_old_hang_ups_by_caller_number_only(db):
    applicant = add_call(name="Carlos Rivera", phone=KNOWN)
    db.execute("INSERT INTO calls (vapi_call_id, applicant_id, raw_payload, needs_review, review_reason, caller_number) "
               "VALUES ('old-known', NULL, '{}', true, 'no_intake', %s), "
               "('old-stranger', NULL, '{}', true, 'no_intake', '+12065550199'), "
               "('old-invalid', NULL, '{}', true, 'invalid_phone', %s)", (KNOWN, KNOWN))
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        conn.execute(MIGRATION.read_text(encoding="utf-8"))
    linked = dict(db.execute("SELECT vapi_call_id, applicant_id FROM calls WHERE vapi_call_id LIKE 'old-%'").fetchall())
    known_id = db.execute("SELECT applicant_id FROM calls WHERE id = %s", (applicant,)).fetchone()[0]
    assert linked == {"old-known": known_id, "old-stranger": None, "old-invalid": None}
