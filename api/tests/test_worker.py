"""Outbox worker against real Postgres and a fake Zoho."""
import copy

import psycopg
import pytest

from app import worker
from app.zoho import ZohoError
from tests.test_calls_api import web  # noqa: F401  (pytest fixture: a logged-in recruiter)


class FakeZoho:
    """Records what it was asked to do; can be told to fail."""

    def __init__(self):
        self.fail_with = None  # a ZohoError or any Exception, raised by every call
        self.note_fails_with = None  # raised by add_note only: the candidate is created, the note is not
        self.candidates = []
        self.known_ids = []  # the known_id passed with each upsert, in order
        self.notes = []

    def upsert_candidate(self, phone, fields, known_id=None):
        if self.fail_with:
            raise self.fail_with
        self.candidates.append((phone, fields))
        self.known_ids.append(known_id)
        return known_id or f"zoho-{phone}"

    def add_note(self, candidate_id, title, content):
        if self.fail_with or self.note_fails_with:
            raise self.fail_with or self.note_fails_with
        self.notes.append((candidate_id, title, content))


@pytest.fixture
def zoho():
    return FakeZoho()


@pytest.fixture
def conn(clean_tables):
    from tests.conftest import TEST_URL
    with psycopg.connect(TEST_URL) as c:
        yield c


def post_call(client, payload, call_id, phone="2065550142"):
    p = copy.deepcopy(payload)
    p["message"]["call"]["id"] = call_id
    p["message"]["toolCalls"][0]["function"]["arguments"]["phoneNumber"] = phone
    assert client.post("/calls", json=p).status_code == 201


def outbox(db):
    return db.execute("SELECT status, attempts, last_error FROM outbox ORDER BY id").fetchall()


def make_due(db):
    db.execute("UPDATE outbox SET next_attempt_at = now() WHERE status = 'pending'")


def test_backoff_doubles_and_is_capped_at_fifteen_minutes():
    assert [worker.backoff_seconds(n) for n in (1, 2, 3, 4)] == [30, 60, 120, 240]
    assert worker.backoff_seconds(6) == 900 and worker.backoff_seconds(50) == 900


def test_nothing_due_returns_none(conn, zoho):
    assert worker.process_one(conn, zoho) is None


def test_success_marks_sent_and_stores_the_zoho_id(client, payload, db, conn, zoho):
    post_call(client, payload, "call-1")
    assert worker.process_one(conn, zoho) == "sent"
    assert outbox(db) == [("sent", 1, None)]
    assert db.execute("SELECT sent_at IS NOT NULL FROM outbox").fetchone()[0] is True
    assert db.execute("SELECT zoho_candidate_id FROM applicants").fetchone()[0] == "zoho-+12065550142"
    (phone, fields), = zoho.candidates
    assert phone == "+12065550142" and fields["Last_Name"] == "Smith" and fields["Source"] == "Phone Call"
    (cid, title, content), = zoho.notes
    assert cid == "zoho-+12065550142" and title == "VAPI Intake — call-1"
    assert "VAPI Call ID: call-1" in content and "Temperature: MEDIUM" in content
    assert "Requested callback: 2026-09-25T10:00:00-07:00" in content


def test_sent_rows_are_not_processed_twice(client, payload, conn, zoho):
    post_call(client, payload, "call-1")
    worker.process_one(conn, zoho)
    assert worker.process_one(conn, zoho) is None
    assert len(zoho.candidates) == 1


def test_transient_error_keeps_the_row_pending_with_backoff(client, payload, db, conn, zoho):
    post_call(client, payload, "call-1")
    zoho.fail_with = ZohoError("retry", "Zoho HTTP 503")
    assert worker.process_one(conn, zoho) == "retry"
    assert outbox(db) == [("pending", 1, "Zoho HTTP 503")]
    wait = db.execute("SELECT extract(epoch FROM next_attempt_at - now()) FROM outbox").fetchone()[0]
    assert 20 < wait <= 30
    assert worker.process_one(conn, zoho) is None  # not due yet: not hammered


def test_permanent_error_marks_failed_and_stops(client, payload, db, conn, zoho):
    post_call(client, payload, "call-1")
    zoho.fail_with = ZohoError("fail", "Zoho INVALID_DATA: bad zip")
    assert worker.process_one(conn, zoho) == "failed"
    assert outbox(db) == [("failed", 1, "Zoho INVALID_DATA: bad zip")]
    make_due(db)
    assert worker.process_one(conn, zoho) is None


def test_unexpected_bug_is_retried_not_marked_failed(client, payload, db, conn, zoho):
    post_call(client, payload, "call-1")
    zoho.fail_with = KeyError("surprise")
    assert worker.process_one(conn, zoho) == "retry"
    status, attempts, error = outbox(db)[0]
    assert status == "pending" and attempts == 1 and "KeyError" in error


def test_crm_down_then_back_no_lead_lost(client, payload, db, conn, zoho):
    """The headline demo: Zoho down, ten drivers call, Zoho recovers, all ten arrive."""
    for i in range(10):
        post_call(client, payload, f"call-{i}", phone=f"20655501{i:02d}")
    zoho.fail_with = ZohoError("retry", "Zoho HTTP 503")
    for _ in range(10):
        assert worker.process_one(conn, zoho) == "retry"
    assert {row[0] for row in outbox(db)} == {"pending"}
    assert db.execute("SELECT count(*) FROM applicants").fetchone()[0] == 10  # nothing lost meanwhile

    zoho.fail_with = None  # Zoho recovers
    make_due(db)
    results = []
    while (r := worker.process_one(conn, zoho)) is not None:
        results.append(r)
    assert results == ["sent"] * 10
    assert {row[0] for row in outbox(db)} == {"sent"}
    assert len(zoho.candidates) == 10


def test_worker_hands_zoho_the_stored_candidate_id_so_a_corrected_phone_creates_no_duplicate(
        client, payload, db, conn, zoho):
    post_call(client, payload, "call-1", phone="2065550142")
    assert worker.process_one(conn, zoho) == "sent"
    assert zoho.known_ids == [None]  # first contact: nothing stored yet, Zoho searches by phone
    stored_id = db.execute("SELECT zoho_candidate_id FROM applicants").fetchone()[0]

    # a recruiter corrects the number in Postgres; the next sync must follow the stored id
    db.execute("UPDATE applicants SET phone_e164 = '+12065550999'")
    post_call(client, payload, "call-2", phone="2065550999")  # lands on the same applicant row
    assert db.execute("SELECT count(*) FROM applicants").fetchone()[0] == 1
    assert worker.process_one(conn, zoho) == "sent"
    assert zoho.known_ids == [None, stored_id]
    assert zoho.candidates[-1][0] == "+12065550999"


def test_repeat_caller_sends_each_call_to_the_same_zoho_candidate(client, payload, db, conn, zoho):
    post_call(client, payload, "call-1")
    post_call(client, payload, "call-2")
    assert [worker.process_one(conn, zoho), worker.process_one(conn, zoho)] == ["sent", "sent"]
    assert len(zoho.notes) == 2 and len({n[0] for n in zoho.notes}) == 1
    assert db.execute("SELECT count(*) FROM applicants").fetchone()[0] == 1


def test_a_row_locked_by_another_worker_is_skipped(client, payload, db, conn, zoho):
    from tests.conftest import TEST_URL
    post_call(client, payload, "call-1")
    with psycopg.connect(TEST_URL) as other:
        with other.transaction():
            other.execute("SELECT id FROM outbox WHERE status = 'pending' FOR UPDATE")
            assert worker.process_one(conn, zoho) is None  # worker B must not double-send
    assert worker.process_one(conn, zoho) == "sent"


# --- C1c step 2b: the worker sends recruiter corrections ------------------------------------

def _synced_applicant_and_call(db):
    """A call whose intake already reached Zoho (the applicant has its Zoho id)."""
    from tests.test_calls_api import add_call
    call_id = add_call("Jane Roe", "+12065550199", temperature="WARM",
                       outbox={"status": "sent", "attempts": 1})
    db.execute("UPDATE applicants SET zoho_candidate_id = 'zoho-1'")
    return call_id


def test_a_correction_updates_the_stored_zoho_candidate_and_notes_every_change(web, db, conn, zoho):
    call_id = _synced_applicant_and_call(db)
    resp = web.patch(f"/api/calls/{call_id}", json={"phone": "(206) 555-0123", "temperature": "HOT"})
    assert resp.status_code == 200

    assert worker.process_one(conn, zoho) == "sent"
    assert zoho.known_ids == ["zoho-1"]                       # followed the stored id, no phone search
    assert zoho.candidates[-1][0] == "+12065550123"            # and sent the corrected phone
    (cid, title, content), = zoho.notes
    assert cid == "zoho-1" and title.startswith("Recruiter correction")
    assert "phone: +12065550199 → +12065550123" in content
    assert "temperature: WARM → HOT" in content
    assert "Corrected by: demo" in content
    assert outbox(db)[-1][0] == "sent"


def test_a_correction_waits_out_a_zoho_outage_and_is_not_lost(web, db, conn, zoho):
    call_id = _synced_applicant_and_call(db)
    web.patch(f"/api/calls/{call_id}", json={"name": "Jane Q. Roe"})
    zoho.fail_with = ZohoError("retry", "Zoho HTTP 503")
    assert worker.process_one(conn, zoho) == "retry"
    assert outbox(db)[-1][:2] == ("pending", 1)

    zoho.fail_with = None
    make_due(db)
    assert worker.process_one(conn, zoho) == "sent"
    assert "name: Jane Roe → Jane Q. Roe" in zoho.notes[-1][2]


def test_an_empty_old_value_reads_as_empty_in_the_note(web, db, conn, zoho):
    call_id = _synced_applicant_and_call(db)
    db.execute("UPDATE applicants SET zip_code = ''")
    web.patch(f"/api/calls/{call_id}", json={"zip_code": "33601"})
    worker.process_one(conn, zoho)
    assert "zip_code: (empty) → 33601" in zoho.notes[-1][2]


# --- the candidate id survives a failed note (review finding F1) --------------------------------

def test_a_failed_note_still_stores_the_candidate_id_so_the_retry_makes_no_duplicate(
        client, payload, db, conn, zoho):
    """Zoho created the candidate, then the note call failed. Without the stored id the retry would search by
    phone, and Zoho's search can lag, so a second candidate could be created for the same driver."""
    post_call(client, payload, "call-1")
    zoho.note_fails_with = ZohoError("retry", "Zoho HTTP 503 on the note")
    assert worker.process_one(conn, zoho) == "retry"
    stored_id = db.execute("SELECT zoho_candidate_id FROM applicants").fetchone()[0]
    assert stored_id == "zoho-+12065550142"  # kept, even though the row is still pending

    zoho.note_fails_with = None
    make_due(db)
    assert worker.process_one(conn, zoho) == "sent"
    assert zoho.known_ids == [None, stored_id]  # the retry reuses the id instead of searching again
    assert len(zoho.candidates) == 2 and len({c[0] for c in zoho.candidates}) == 1
    assert outbox(db) == [("sent", 2, None)]


def test_a_permanent_note_failure_also_keeps_the_candidate_id(client, payload, db, conn, zoho):
    post_call(client, payload, "call-1")
    zoho.note_fails_with = ZohoError("fail", "Zoho 400: INVALID_DATA")
    assert worker.process_one(conn, zoho) == "failed"
    assert db.execute("SELECT zoho_candidate_id FROM applicants").fetchone()[0] == "zoho-+12065550142"


def test_a_failed_candidate_write_stores_nothing(client, payload, db, conn, zoho):
    post_call(client, payload, "call-1")
    zoho.fail_with = ZohoError("retry", "Zoho HTTP 503")
    assert worker.process_one(conn, zoho) == "retry"
    assert db.execute("SELECT zoho_candidate_id FROM applicants").fetchone()[0] is None


def resend_with_new_time(client, payload, call_id, when):
    p = copy.deepcopy(payload)
    p["message"]["call"]["id"] = call_id
    p["message"]["toolCalls"][0]["function"]["arguments"]["phoneNumber"] = "2065550142"
    p["message"]["toolCalls"][0]["function"]["arguments"]["preferredCallbackTime"] = when
    return client.post("/calls", json=p)


def test_a_changed_callback_time_after_the_zoho_sync_is_sent_again_with_the_new_time(client, payload, db, conn, zoho):
    post_call(client, payload, "call-1")
    worker.process_one(conn, zoho)                      # the first (rejected) time is now in Zoho
    assert resend_with_new_time(client, payload, "call-1", "2026-09-28T11:00:00").status_code == 200
    assert outbox(db) == [("pending", 0, None)]         # queued again, attempts reset
    assert worker.process_one(conn, zoho) == "sent"
    assert len(zoho.candidates) == 2 and zoho.known_ids == [None, "zoho-+12065550142"]  # same candidate, no duplicate
    assert "Requested callback: 2026-09-28T11:00:00-07:00" in zoho.notes[-1][2]


def test_a_changed_callback_time_before_the_zoho_sync_just_waits_for_the_one_pending_send(client, payload, db, conn, zoho):
    post_call(client, payload, "call-1")
    resend_with_new_time(client, payload, "call-1", "2026-09-28T11:00:00")
    assert outbox(db) == [("pending", 0, None)]
    worker.process_one(conn, zoho)
    assert len(zoho.notes) == 1 and "2026-09-28T11:00:00-07:00" in zoho.notes[0][2]  # one note, latest time


def test_the_same_callback_time_again_does_not_queue_another_zoho_send(client, payload, db, conn, zoho):
    post_call(client, payload, "call-1")
    worker.process_one(conn, zoho)
    resend_with_new_time(client, payload, "call-1", "2026-09-25T10:00:00")  # same as the fixture's time
    assert outbox(db) == [("sent", 1, None)]


def test_a_failed_sync_is_not_revived_by_a_changed_callback_time(client, payload, db, conn, zoho):
    post_call(client, payload, "call-1")
    zoho.fail_with = ZohoError("fail", "bad request")
    worker.process_one(conn, zoho)
    resend_with_new_time(client, payload, "call-1", "2026-09-28T11:00:00")
    assert outbox(db)[0][0] == "failed"
