"""C2 backend: GET /api/todo, the data behind the To do page. Written before the code.

attention = one row per CALL that is broken (needs_review, or its Zoho save failed).
call_back = one row per PERSON who should be phoned (follow-up 'to_call', or a new call since).
"""
import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.conftest import TEST_API_KEY, TEST_URL
from tests.test_calls_api import add_call, admin_web, web  # noqa: F401  (web and admin_web are pytest fixtures)


def sql(statement, params=()):
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        return conn.execute(statement, params).fetchall() if statement.lstrip().upper().startswith("SELECT") \
            else conn.execute(statement, params)


def set_follow_up(phone, status, minutes_ago=5):
    sql("UPDATE applicants SET follow_up_status = %s, follow_up_updated_at = now() - make_interval(mins => %s) "
        "WHERE phone_e164 = %s", (status, minutes_ago, phone))


def set_callback_at(call_id, hours_from_now):
    sql("UPDATE calls SET preferred_callback_at = now() + make_interval(hours => %s) WHERE id = %s",
        (hours_from_now, call_id))


def call_back_names(resp):
    return [row["applicant"]["name"] for row in resp.json()["call_back"]]


def attention_ids(resp):
    return [row["id"] for row in resp.json()["attention"]]


# --- access ---------------------------------------------------------------------------------

def test_todo_needs_a_login(clean_tables):
    from app.main import app
    assert TestClient(app).get("/api/todo").status_code == 401
    assert TestClient(app, headers={"X-API-Key": TEST_API_KEY}).get("/api/todo").status_code == 401


def test_empty_database_gives_empty_lists(web):
    body = web.get("/api/todo").json()
    assert body["attention"] == [] and body["call_back"] == []
    assert body["summary"] == {"calls_today": 0, "hot_waiting": 0, "to_call": 0, "sync_problems": 0}


# --- Needs attention: one row per call, only broken calls ------------------------------------

def test_needs_review_call_without_a_person_is_in_attention_not_call_back(web):
    broken = add_call(name="Unknown", phone=None, needs_review=True, review_reason="invalid_phone")
    r = web.get("/api/todo")
    assert attention_ids(r) == [broken]
    assert r.json()["attention"][0]["review_reason"] == "invalid_phone"
    assert r.json()["call_back"] == []


def test_failed_zoho_save_is_in_attention(admin_web):
    failed = add_call(name="Marcus", phone="+13125550148", outbox={"status": "failed", "last_error": "401"})
    r = admin_web.get("/api/todo")
    assert attention_ids(r) == [failed]
    assert r.json()["attention"][0]["sync"]["last_error"] == "401"


def test_clean_calls_are_never_in_attention(web):
    add_call(name="Luis", phone="+16025550121", outbox={"status": "sent"})
    add_call(name="Ana", phone="+16025550122", outbox={"status": "pending"})  # waiting, not broken
    add_call(name="Bo", phone="+16025550123")
    assert web.get("/api/todo").json()["attention"] == []


def test_a_corrected_call_leaves_attention(web):
    call_id = add_call(name="Kim", phone="+16025550124", needs_review=False, review_reason=None)
    assert call_id not in attention_ids(web.get("/api/todo"))


def test_one_failed_call_of_a_person_who_also_needs_a_phone_call_appears_in_both(web):
    """Dana: Monday fine, Tuesday's Zoho save failed. Attention has the Tuesday call; call_back has Dana once."""
    add_call(name="Dana", phone="+12145550167", minutes_ago=1500)
    tuesday = add_call(name="Dana", phone="+12145550167", minutes_ago=10, outbox={"status": "failed"})
    r = web.get("/api/todo")
    assert attention_ids(r) == [tuesday]
    assert call_back_names(r) == ["Dana"]


# --- Call back: one row per person -----------------------------------------------------------

def test_three_calls_from_one_person_make_one_row_with_the_count(web):
    for minutes in (3000, 2000, 10):
        add_call(name="Luis", phone="+16025550121", minutes_ago=minutes)
    rows = web.get("/api/todo").json()["call_back"]
    assert len(rows) == 1 and rows[0]["call_count"] == 3


def test_a_call_without_a_person_never_appears_in_call_back(web):
    add_call(name="Unknown", phone=None, needs_review=True, review_reason="invalid_phone")
    assert web.get("/api/todo").json()["call_back"] == []


@pytest.mark.parametrize("status", ["called", "no_answer", "done"])
def test_people_already_followed_up_are_not_listed(web, status):
    add_call(name="Ray", phone="+19015550139", minutes_ago=60)
    set_follow_up("+19015550139", status, minutes_ago=5)  # the follow-up is later than the call
    assert web.get("/api/todo").json()["call_back"] == []


def test_a_new_call_after_the_follow_up_brings_the_person_back_with_the_marker(web):
    add_call(name="Ray", phone="+19015550139", minutes_ago=100)
    set_follow_up("+19015550139", "done", minutes_ago=50)
    assert web.get("/api/todo").json()["call_back"] == []
    add_call(name="Ray", phone="+19015550139", minutes_ago=1)  # calls again after being marked done
    row = web.get("/api/todo").json()["call_back"][0]
    assert row["applicant"]["name"] == "Ray" and row["new_call_since"] is True
    assert row["applicant"]["follow_up"]["status"] == "done"


def test_row_carries_the_callback_phone_and_the_latest_calls_callback_time(web):
    add_call(name="Dana", phone="+12145550167", minutes_ago=500)
    latest = add_call(name="Dana", phone="+12145550167", minutes_ago=5)
    set_callback_at(latest, 3)
    sql("UPDATE applicants SET callback_phone = '+16727274656' WHERE phone_e164 = '+12145550167'")
    row = web.get("/api/todo").json()["call_back"][0]
    assert row["applicant"]["callback_phone"] == "+16727274656"
    assert row["preferred_callback_at"] is not None
    assert row["latest_call_at"] is not None


def test_order_is_hot_first_then_earliest_callback_then_no_callback_time_last(web):
    add_call(name="Cold Ray", phone="+19015550139", temperature="COLD")
    late = add_call(name="Hot Late", phone="+16025550121", temperature="HOT")
    early = add_call(name="Hot Early", phone="+16025550122", temperature="HOT")
    none = add_call(name="Hot None", phone="+16025550123", temperature="HOT")
    add_call(name="Medium Kim", phone="+14045550185", temperature="MEDIUM")
    set_callback_at(late, 5)
    set_callback_at(early, 1)
    assert call_back_names(web.get("/api/todo")) == [
        "Hot Early", "Hot Late", "Hot None", "Medium Kim", "Cold Ray"]


# --- the numbers strip -----------------------------------------------------------------------

def test_summary_counts(web):
    add_call(name="Hot", phone="+16025550121", temperature="HOT")
    add_call(name="Warm", phone="+16025550122", temperature="WARM")
    add_call(name="Old", phone="+16025550123", temperature="HOT", minutes_ago=60 * 24 * 3)  # 3 days ago
    add_call(name="Marcus", phone="+13125550148", temperature="COLD", outbox={"status": "failed"})
    add_call(name="Unknown", phone=None, needs_review=True, review_reason="invalid_phone")
    set_follow_up("+16025550123", "done")  # Old is already handled
    s = web.get("/api/todo").json()["summary"]
    assert s["to_call"] == 3          # Hot, Warm, Marcus
    assert s["hot_waiting"] == 1      # Hot (Old is HOT but already done)
    assert s["sync_problems"] == 1    # Marcus
    assert s["calls_today"] == 4      # everything except the 3-day-old call
