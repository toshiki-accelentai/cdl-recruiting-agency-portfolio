"""Outbox worker against real Postgres and a fake Zoho."""
import copy

import psycopg
import pytest

from app import worker
from app.zoho import ZohoError


class FakeZoho:
    """Records what it was asked to do; can be told to fail."""

    def __init__(self):
        self.fail_with = None  # a ZohoError or any Exception, raised by every call
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
        if self.fail_with:
            raise self.fail_with
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
