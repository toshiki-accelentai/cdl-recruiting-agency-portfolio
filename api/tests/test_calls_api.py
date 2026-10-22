"""C1b: GET /api/calls (list, sort, filter, paging) and GET /api/calls/{id}. Written before the code."""
import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.conftest import TEST_API_KEY, TEST_URL

PASSWORD = "correct horse battery"


@pytest.fixture
def web(clean_tables):
    """A logged-in recruiter's browser. It sends no X-API-Key."""
    from app.auth import create_user
    from app.main import app
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        create_user(conn, "demo", PASSWORD, "recruiter")
    client = TestClient(app)
    assert client.post("/login", data={"username": "demo", "password": PASSWORD}).status_code == 200
    return client


@pytest.fixture
def admin_web(clean_tables):
    """A logged-in admin's browser: the only role that sees the worker's error text and the Zoho id."""
    from app.auth import create_user
    from app.main import app
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        create_user(conn, "owner", PASSWORD, "admin")
    client = TestClient(app)
    assert client.post("/login", data={"username": "owner", "password": PASSWORD}).status_code == 200
    return client


def add_call(name="Test Driver", phone="+12065550101", temperature="WARM", minutes_ago=0,
             needs_review=False, review_reason=None, outbox=None, vapi_id=None):
    """Insert one call (and its applicant/outbox) straight into the database; returns the call id.

    outbox is None (no row) or a dict like {"status": "pending", "attempts": 2, "last_error": "x"}.
    """
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        applicant_id = None
        if phone is not None:
            applicant_id = conn.execute(
                "INSERT INTO applicants (name, phone_e164, city, state, zip_code, experience, readiness, "
                "temperature) VALUES (%s, %s, 'Tampa', 'FL', '33601', '5 years', 'next week', %s) "
                "ON CONFLICT (phone_e164) DO UPDATE SET name = EXCLUDED.name RETURNING id",
                (name, phone, temperature)).fetchone()[0]
        call_id = conn.execute(
            "INSERT INTO calls (vapi_call_id, applicant_id, raw_payload, needs_review, review_reason, "
            "created_at) VALUES (%s, %s, '{\"secret\": \"do-not-show\"}', %s, %s, "
            "now() - make_interval(mins => %s)) RETURNING id",
            (vapi_id or f"vapi-{name}-{minutes_ago}-{needs_review}", applicant_id, needs_review,
             review_reason, minutes_ago)).fetchone()[0]
        if outbox is not None:
            conn.execute(
                "INSERT INTO outbox (call_id, applicant_id, status, attempts, last_error) "
                "VALUES (%s, %s, %s, %s, %s)",
                (call_id, applicant_id, outbox.get("status", "pending"), outbox.get("attempts", 0),
                 outbox.get("last_error")))
        return call_id


def ids(resp):
    return [item["id"] for item in resp.json()["items"]]


# --- access ---------------------------------------------------------------------------------

def test_list_and_detail_need_a_login(clean_tables):
    from app.main import app
    anon = TestClient(app)
    call_id = add_call()
    assert anon.get("/api/calls").status_code == 401
    assert anon.get(f"/api/calls/{call_id}").status_code == 401


def test_the_n8n_api_key_does_not_open_the_dashboard(clean_tables):
    from app.main import app
    keyed = TestClient(app, headers={"X-API-Key": TEST_API_KEY})
    assert keyed.get("/api/calls").status_code == 401


# --- list: order, shape ---------------------------------------------------------------------

def test_newest_first_is_the_default(web):
    old = add_call("Old", "+12065550101", minutes_ago=30)
    new = add_call("New", "+12065550102", minutes_ago=1)
    mid = add_call("Mid", "+12065550103", minutes_ago=10)
    assert ids(web.get("/api/calls")) == [new, mid, old]


def test_sort_oldest(web):
    old = add_call("Old", "+12065550101", minutes_ago=30)
    new = add_call("New", "+12065550102", minutes_ago=1)
    assert ids(web.get("/api/calls?sort=oldest")) == [old, new]


def test_sort_needs_review_puts_flagged_calls_first_then_newest(web):
    plain_new = add_call("A", "+12065550101", minutes_ago=1)
    flagged_old = add_call("B", "+12065550102", minutes_ago=50, needs_review=True,
                           review_reason="missing_name")
    flagged_new = add_call("C", "+12065550103", minutes_ago=20, needs_review=True,
                           review_reason="invalid_phone")
    assert ids(web.get("/api/calls?sort=needs_review")) == [flagged_new, flagged_old, plain_new]


def test_sort_temperature_is_hot_medium_warm_cold_then_newest(web):
    cold = add_call("Cold", "+12065550101", temperature="COLD", minutes_ago=1)
    warm = add_call("Warm", "+12065550102", temperature="WARM", minutes_ago=2)
    hot_old = add_call("HotOld", "+12065550103", temperature="HOT", minutes_ago=40)
    hot_new = add_call("HotNew", "+12065550104", temperature="HOT", minutes_ago=5)
    medium = add_call("Medium", "+12065550105", temperature="MEDIUM", minutes_ago=3)
    assert ids(web.get("/api/calls?sort=temperature")) == [hot_new, hot_old, medium, warm, cold]


def test_unknown_sort_is_rejected(web):
    assert web.get("/api/calls?sort=banana").status_code == 422


def test_item_shape_includes_applicant_and_zoho_sync_state(admin_web):
    call_id = add_call("Jane Roe", "+12065550199", temperature="HOT", needs_review=False,
                       outbox={"status": "pending", "attempts": 3, "last_error": "zoho down"})
    item = admin_web.get("/api/calls").json()["items"][0]
    assert item["id"] == call_id
    assert item["needs_review"] is False
    assert item["applicant"]["name"] == "Jane Roe"
    assert item["applicant"]["phone"] == "+12065550199"
    assert item["applicant"]["temperature"] == "HOT"
    assert item["applicant"]["city"] == "Tampa"
    assert item["sync"]["status"] == "pending"
    assert item["sync"]["attempts"] == 3
    assert item["sync"]["last_error"] == "zoho down"
    assert "next_attempt_at" in item["sync"]


def test_raw_payload_is_never_returned(web):
    call_id = add_call()
    assert "do-not-show" not in web.get("/api/calls").text
    assert "do-not-show" not in web.get(f"/api/calls/{call_id}").text


def test_call_without_a_usable_phone_is_listed_with_no_applicant_and_no_sync(web):
    call_id = add_call(phone=None, needs_review=True, review_reason="invalid_phone")
    item = web.get("/api/calls").json()["items"][0]
    assert item["id"] == call_id
    assert item["applicant"] is None
    assert item["sync"] is None
    assert item["review_reason"] == "invalid_phone"


# --- list: filter, paging -------------------------------------------------------------------

def test_filter_needs_review(web):
    add_call("A", "+12065550101")
    flagged = add_call("B", "+12065550102", needs_review=True, review_reason="missing_name")
    assert ids(web.get("/api/calls?needs_review=true")) == [flagged]


def test_filter_by_sync_status(web):
    add_call("Sent", "+12065550101", outbox={"status": "sent", "attempts": 1})
    pending = add_call("Pending", "+12065550102", outbox={"status": "pending", "attempts": 2})
    add_call("Failed", "+12065550103", outbox={"status": "failed", "attempts": 9})
    assert ids(web.get("/api/calls?sync=pending")) == [pending]


def test_unknown_sync_filter_is_rejected(web):
    assert web.get("/api/calls?sync=banana").status_code == 422


def test_paging_and_total(web):
    created = [add_call(f"D{i}", f"+1206555010{i}", minutes_ago=i) for i in range(5)]  # newest first
    first = web.get("/api/calls?limit=2").json()
    second = web.get("/api/calls?limit=2&offset=2").json()
    assert [i["id"] for i in first["items"]] == created[:2]
    assert [i["id"] for i in second["items"]] == created[2:4]
    assert first["total"] == second["total"] == 5


def test_total_counts_the_filtered_set_not_just_the_page(web):
    for i in range(3):
        add_call(f"F{i}", f"+1206555020{i}", needs_review=True, review_reason="missing_name")
    add_call("Fine", "+12065550299")
    body = web.get("/api/calls?needs_review=true&limit=1").json()
    assert len(body["items"]) == 1
    assert body["total"] == 3


@pytest.mark.parametrize("query", ["limit=0", "limit=201", "limit=-1", "offset=-1"])
def test_bad_paging_is_rejected(web, query):
    assert web.get(f"/api/calls?{query}").status_code == 422


# --- detail ---------------------------------------------------------------------------------

def test_detail_returns_one_call(web):
    call_id = add_call("Jane Roe", "+12065550199", outbox={"status": "sent", "attempts": 1})
    body = web.get(f"/api/calls/{call_id}").json()
    assert body["id"] == call_id
    assert body["applicant"]["name"] == "Jane Roe"
    assert body["sync"]["status"] == "sent"


def test_detail_of_a_missing_call_is_404(web):
    assert web.get("/api/calls/999999").status_code == 404
