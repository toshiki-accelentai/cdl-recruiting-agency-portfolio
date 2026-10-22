"""C2: GET /api/applicants/{id}, the data behind the Applicant detail page. Written before the code.

One person: their profile, every call (newest first, with Zoho sync state), and the change history.
"""
import psycopg
from fastapi.testclient import TestClient

from tests.conftest import TEST_API_KEY, TEST_URL
from tests.test_calls_api import add_call, admin_web, web  # noqa: F401  (web and admin_web are pytest fixtures)


def applicant_id(phone):
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        return conn.execute("SELECT id FROM applicants WHERE phone_e164 = %s", (phone,)).fetchone()[0]


# --- access ---------------------------------------------------------------------------------

def test_detail_needs_a_login(clean_tables):
    from app.main import app
    add_call(phone="+12145550167")
    pid = applicant_id("+12145550167")
    assert TestClient(app).get(f"/api/applicants/{pid}").status_code == 401
    assert TestClient(app, headers={"X-API-Key": TEST_API_KEY}).get(f"/api/applicants/{pid}").status_code == 401


def test_unknown_applicant_is_404(web):
    assert web.get("/api/applicants/999999").status_code == 404


# --- the profile ----------------------------------------------------------------------------

def test_profile_fields(admin_web):
    add_call(name="Dana Brooks", phone="+12145550167", temperature="HOT")
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        conn.execute("UPDATE applicants SET callback_phone = '+16727274656', zoho_candidate_id = 'Z123', "
                     "follow_up_note = 'After 6 PM' WHERE phone_e164 = '+12145550167'")
    body = admin_web.get(f"/api/applicants/{applicant_id('+12145550167')}").json()
    person = body["applicant"]
    assert person["name"] == "Dana Brooks" and person["phone"] == "+12145550167"
    assert person["callback_phone"] == "+16727274656" and person["zoho_candidate_id"] == "Z123"
    assert person["temperature"] == "HOT" and person["city"] == "Tampa" and person["state"] == "FL"
    assert person["follow_up"]["status"] == "to_call" and person["follow_up"]["note"] == "After 6 PM"
    assert person["follow_up"]["new_call_since"] is False


def test_new_call_marker_after_a_follow_up(web):
    add_call(phone="+12145550167", minutes_ago=100)
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        conn.execute("UPDATE applicants SET follow_up_status = 'called', "
                     "follow_up_updated_at = now() - interval '50 minutes'")
    add_call(phone="+12145550167", minutes_ago=1)
    follow_up = web.get(f"/api/applicants/{applicant_id('+12145550167')}").json()["applicant"]["follow_up"]
    assert follow_up["status"] == "called" and follow_up["new_call_since"] is True


# --- the calls ------------------------------------------------------------------------------

def test_calls_are_newest_first_with_sync_state_and_no_raw_payload(admin_web):
    old = add_call(phone="+12145550167", minutes_ago=3000, outbox={"status": "sent", "attempts": 1})
    new = add_call(phone="+12145550167", minutes_ago=5, outbox={"status": "failed", "attempts": 5, "last_error": "401"},
                   needs_review=True, review_reason="missing_name")
    response = admin_web.get(f"/api/applicants/{applicant_id('+12145550167')}")
    calls = response.json()["calls"]
    assert [c["id"] for c in calls] == [new, old]
    assert calls[0]["sync"]["status"] == "failed" and calls[0]["sync"]["last_error"] == "401"
    assert calls[0]["needs_review"] is True and calls[0]["review_reason"] == "missing_name"
    assert calls[1]["sync"]["status"] == "sent"
    assert "do-not-show" not in response.text  # add_call plants a secret in raw_payload


def test_other_peoples_calls_are_not_included(web):
    mine = add_call(name="Dana", phone="+12145550167")
    add_call(name="Luis", phone="+16025550121")
    calls = web.get(f"/api/applicants/{applicant_id('+12145550167')}").json()["calls"]
    assert [c["id"] for c in calls] == [mine]


# --- the change history ---------------------------------------------------------------------

def test_history_lists_follow_up_changes_and_corrections_newest_first(web):
    call_id = add_call(name="Dana Brooks", phone="+12145550167")
    pid = applicant_id("+12145550167")
    assert web.patch(f"/api/calls/{call_id}", json={"city": "Dallas"}).status_code == 200
    assert web.patch(f"/api/applicants/{pid}/follow-up", json={"status": "called"}).status_code == 200
    history = web.get(f"/api/applicants/{pid}").json()["history"]
    assert [h["action"] for h in history] == ["update_follow_up", "correct_applicant"]
    assert all(h["username"] == "demo" for h in history)
    assert history[0]["changes"]["follow_up_status"] == {"from": "to_call", "to": "called"}
    assert history[1]["changes"]["city"] == {"from": "Tampa", "to": "Dallas"}


def test_history_is_empty_for_an_untouched_applicant(web):
    add_call(phone="+12145550167")
    assert web.get(f"/api/applicants/{applicant_id('+12145550167')}").json()["history"] == []


# --- C1e: what the end-of-call report added ---------------------------------------------------

LINES = [{"speaker": "agent", "text": "Thanks for calling.", "start": 0.4},
         {"speaker": "driver", "text": "Hi there.", "start": 6.2}]


def add_report(call_id, summary="Wants regional work.", has_recording=True, caller="+14155550123"):
    import json
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        conn.execute("UPDATE calls SET summary = %s, transcript = %s::jsonb, has_recording = %s, "
                     "caller_number = %s, report_received_at = now() WHERE id = %s",
                     (summary, json.dumps(LINES), has_recording, caller, call_id))


def test_detail_calls_carry_summary_transcript_and_recording_flag(web):
    with_report = add_call(phone="+12145550167", minutes_ago=5)
    without = add_call(phone="+12145550167", minutes_ago=500)
    add_report(with_report)
    calls = web.get(f"/api/applicants/{applicant_id('+12145550167')}").json()["calls"]
    assert calls[0]["id"] == with_report
    assert calls[0]["summary"] == "Wants regional work." and calls[0]["transcript"] == LINES
    assert calls[0]["has_recording"] is True and calls[0]["caller_number"] == "+14155550123"
    assert calls[1]["id"] == without
    assert calls[1]["summary"] is None and calls[1]["transcript"] is None and calls[1]["has_recording"] is False


def test_list_and_todo_rows_carry_the_summary_but_never_the_transcript(web):
    call_id = add_call(name="Unknown", phone=None, needs_review=True, review_reason="no_intake")
    add_report(call_id)
    listed = web.get("/api/calls").json()["items"][0]
    attention = web.get("/api/todo").json()["attention"][0]
    detail = web.get(f"/api/calls/{call_id}").json()
    for item in (listed, attention, detail):
        assert item["summary"] == "Wants regional work." and item["has_recording"] is True
        assert item["caller_number"] == "+14155550123"
        assert "transcript" not in item
