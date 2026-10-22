"""Security review findings 3, 4 and 5 (docs/SECURITY-REVIEW.md), written before the code.

3. The worker's error text (it can carry Zoho's wording) is shown to an admin only.
4. The raw Zoho candidate id is shown to an admin only; everyone gets a plain yes/no "has a Zoho record".
5. A logged-in user can only write so fast (per user, sliding window), so one login cannot flood the audit log.
"""
import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.conftest import TEST_URL
from tests.test_calls_api import PASSWORD, add_call, web  # noqa: F401  (web is a pytest fixture)

SECRET_ERROR = "zoho 400: INVALID_DATA internal-detail-xyz"
SECRET_ID = "870474000000683001"


@pytest.fixture
def admin(clean_tables):
    from app.auth import create_user
    from app.main import app
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        create_user(conn, "owner", PASSWORD, "admin")
    client = TestClient(app)
    assert client.post("/login", data={"username": "owner", "password": PASSWORD}).status_code == 200
    return client


def failed_call_with_zoho_id():
    call_id = add_call(name="Marcus Hill", phone="+13125550148", outbox={"status": "failed", "attempts": 5,
                                                                         "last_error": SECRET_ERROR})
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        conn.execute("UPDATE applicants SET zoho_candidate_id = %s", (SECRET_ID,))
        applicant_id = conn.execute("SELECT applicant_id FROM calls WHERE id = %s", (call_id,)).fetchone()[0]
    return call_id, applicant_id


def read_everywhere(client, call_id, applicant_id):
    return [client.get(path).text for path in
            ("/api/calls", f"/api/calls/{call_id}", "/api/todo", f"/api/applicants/{applicant_id}")]


# --- findings 3 and 4 --------------------------------------------------------------------------

def test_a_recruiter_never_sees_the_error_text_or_the_zoho_id(web):
    call_id, applicant_id = failed_call_with_zoho_id()
    for body in read_everywhere(web, call_id, applicant_id):
        assert SECRET_ERROR not in body and "internal-detail" not in body, body
        assert SECRET_ID not in body and "zoho_candidate_id" not in body and "last_error" not in body, body


def test_an_admin_still_sees_both(admin):
    call_id, applicant_id = failed_call_with_zoho_id()
    bodies = read_everywhere(admin, call_id, applicant_id)
    assert all(SECRET_ERROR in b for b in (bodies[0], bodies[1], bodies[2], bodies[3]))
    assert SECRET_ID in bodies[3] and SECRET_ID in bodies[2] and SECRET_ID in bodies[0]


def test_a_recruiter_still_sees_that_the_sync_failed_and_how_many_tries(web):
    call_id, _ = failed_call_with_zoho_id()
    sync = web.get(f"/api/calls/{call_id}").json()["sync"]
    assert sync["status"] == "failed" and sync["attempts"] == 5


def test_everyone_gets_a_plain_yes_or_no_for_a_zoho_record(web):
    call_id, applicant_id = failed_call_with_zoho_id()
    assert web.get(f"/api/applicants/{applicant_id}").json()["applicant"]["has_zoho_record"] is True
    other = add_call(name="No Record", phone="+14045550133")
    other_applicant = web.get(f"/api/calls/{other}").json()["applicant"]["id"]
    assert web.get(f"/api/applicants/{other_applicant}").json()["applicant"]["has_zoho_record"] is False


# --- finding 5 ---------------------------------------------------------------------------------

def patch_follow_up(client, applicant_id, status="called"):
    return client.patch(f"/api/applicants/{applicant_id}/follow-up", json={"status": status})


def test_writes_are_limited_per_user_with_a_retry_after(web):
    from app.throttle import MAX_WRITES
    _, applicant_id = failed_call_with_zoho_id()
    codes = [patch_follow_up(web, applicant_id, "called" if i % 2 else "no_answer").status_code
             for i in range(MAX_WRITES + 3)]
    assert codes[:MAX_WRITES] == [200] * MAX_WRITES
    assert codes[MAX_WRITES:] == [429] * 3
    assert int(patch_follow_up(web, applicant_id).headers["Retry-After"]) >= 1


def test_the_limit_is_per_user_not_shared(web, admin):
    from app.throttle import MAX_WRITES
    _, applicant_id = failed_call_with_zoho_id()
    for _ in range(MAX_WRITES):
        patch_follow_up(web, applicant_id)
    assert patch_follow_up(web, applicant_id).status_code == 429
    assert patch_follow_up(admin, applicant_id, "done").status_code == 200


def test_the_limit_covers_call_corrections_too(web):
    from app.throttle import MAX_WRITES
    call_id, _ = failed_call_with_zoho_id()
    codes = [web.patch(f"/api/calls/{call_id}", json={"city": f"Tampa{i}"}).status_code for i in range(MAX_WRITES + 2)]
    assert codes[-1] == 429 and codes[0] == 200


def test_reading_is_never_limited(web):
    from app.throttle import MAX_WRITES
    _, applicant_id = failed_call_with_zoho_id()
    for _ in range(MAX_WRITES + 5):
        assert web.get("/api/todo").status_code == 200


def test_the_window_slides_so_a_wait_ends():
    from app.throttle import WriteThrottle
    now = [100.0]
    limiter = WriteThrottle(clock=lambda: now[0], max_writes=3, window_seconds=60)
    assert [limiter.hit(1) for _ in range(3)] == [0, 0, 0]
    assert limiter.hit(1) >= 1
    now[0] += 61
    assert limiter.hit(1) == 0


def test_the_answer_to_a_correction_hides_them_from_a_recruiter_too(web):
    call_id, _ = failed_call_with_zoho_id()
    r = web.patch(f"/api/calls/{call_id}", json={"city": "Orlando"})
    assert r.status_code == 200
    assert SECRET_ID not in r.text and "zoho_candidate_id" not in r.text and "last_error" not in r.text and SECRET_ERROR not in r.text


def test_the_answer_to_a_correction_still_shows_an_admin(admin):
    call_id, _ = failed_call_with_zoho_id()
    r = admin.patch(f"/api/calls/{call_id}", json={"city": "Orlando"})
    assert r.status_code == 200 and SECRET_ID in r.text


def test_refused_attempts_do_not_extend_the_wait():
    """Hammering the button while blocked must not push the end of the wait further away."""
    from app.throttle import WriteThrottle
    now = [0.0]
    limiter = WriteThrottle(clock=lambda: now[0], max_writes=3, window_seconds=60)
    assert [limiter.hit(1) for _ in range(3)] == [0, 0, 0]  # all at t=0
    for moment in (10, 30, 59):
        now[0] = moment
        assert limiter.hit(1) >= 1  # refused
    now[0] = 61  # the three real writes have left the window
    assert limiter.hit(1) == 0
