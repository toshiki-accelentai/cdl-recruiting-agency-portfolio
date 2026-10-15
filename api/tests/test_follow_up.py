"""C1d: follow-up status on the applicant, and the 'new call since last follow-up' marker."""
import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.conftest import TEST_API_KEY, TEST_URL
from tests.test_calls_api import add_call, web  # noqa: F401  (web is a pytest fixture)


def q(sql, params=()):
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        cur = conn.execute(sql, params)
        return cur.fetchall() if cur.description else None


def applicant_id():
    return q("SELECT id FROM applicants ORDER BY id LIMIT 1")[0][0]


def set_follow_up(web, applicant, **body):
    return web.patch(f"/api/applicants/{applicant}/follow-up", json=body)


def first_item(web, query=""):
    return web.get(f"/api/calls{query}").json()["items"][0]


# --- access and validation ------------------------------------------------------------------

def test_follow_up_needs_a_login_and_the_n8n_key_is_not_enough(clean_tables):
    from app.main import app
    add_call()
    url = f"/api/applicants/{applicant_id()}/follow-up"
    assert TestClient(app).patch(url, json={"status": "called"}).status_code == 401
    keyed = TestClient(app, headers={"X-API-Key": TEST_API_KEY})
    assert keyed.patch(url, json={"status": "called"}).status_code == 401


def test_unknown_applicant_is_404(web):
    assert set_follow_up(web, 999999, status="called").status_code == 404


@pytest.mark.parametrize("body", [
    {},
    {"status": "maybe"},
    {"note": "x" * 501},
    {"status": "called", "applicant_id": 5},   # a valid field must not smuggle in a forbidden one
])
def test_bad_input_is_rejected_and_changes_nothing(web, body):
    add_call()
    assert set_follow_up(web, applicant_id(), **body).status_code == 422
    assert q("SELECT follow_up_status, follow_up_note FROM applicants") == [("to_call", "")]
    assert q("SELECT count(*) FROM audit_log") == [(0,)]


# --- setting a status -----------------------------------------------------------------------

def test_a_new_applicant_starts_as_to_call_with_no_marker(web):
    add_call()
    follow_up = first_item(web)["applicant"]["follow_up"]
    assert follow_up == {"status": "to_call", "note": "", "updated_at": None,
                         "new_call_since": False}


def test_setting_a_status_saves_it_audits_it_and_does_not_touch_zoho(web):
    add_call()
    resp = set_follow_up(web, applicant_id(), status="called")
    assert resp.status_code == 200 and resp.json()["status"] == "called"
    assert q("SELECT follow_up_status, follow_up_updated_at IS NOT NULL FROM applicants") == [("called", True)]
    (action, changes), = q("SELECT action, changes FROM audit_log")
    assert action == "update_follow_up"
    assert changes == {"follow_up_status": {"from": "to_call", "to": "called"}}
    assert q("SELECT count(*) FROM outbox") == [(0,)]      # follow-ups are internal: nothing is sent to Zoho


def test_a_note_can_be_saved_alone_and_leaves_the_status_alone(web):
    add_call()
    set_follow_up(web, applicant_id(), status="no_answer")
    resp = set_follow_up(web, applicant_id(), note="Try again after 5pm")
    assert resp.json()["status"] == "no_answer" and resp.json()["note"] == "Try again after 5pm"


def test_saving_the_same_values_again_writes_no_audit_row_and_keeps_the_time(web):
    add_call()
    set_follow_up(web, applicant_id(), status="called")
    (first_time,) = q("SELECT follow_up_updated_at FROM applicants")[0]
    assert set_follow_up(web, applicant_id(), status="called").status_code == 200
    assert q("SELECT count(*) FROM audit_log") == [(1,)]
    assert q("SELECT follow_up_updated_at FROM applicants")[0][0] == first_time


def test_two_calls_from_the_same_person_share_one_status(web):
    add_call("Jane Roe", "+12065550199", minutes_ago=60)
    add_call("Jane Roe", "+12065550199", minutes_ago=5, vapi_id="second-call")
    set_follow_up(web, applicant_id(), status="done")
    statuses = [i["applicant"]["follow_up"]["status"] for i in web.get("/api/calls").json()["items"]]
    assert statuses == ["done", "done"]


# --- the marker -----------------------------------------------------------------------------

def test_a_call_after_the_last_follow_up_shows_the_marker(web):
    add_call(minutes_ago=5)
    q("UPDATE applicants SET follow_up_status = 'done', "
      "follow_up_updated_at = now() - interval '10 minutes'")
    follow_up = first_item(web)["applicant"]["follow_up"]
    assert follow_up["status"] == "done"          # the new call did NOT reset the status
    assert follow_up["new_call_since"] is True


def test_a_call_before_the_last_follow_up_shows_no_marker(web):
    add_call(minutes_ago=30)
    q("UPDATE applicants SET follow_up_status = 'called', "
      "follow_up_updated_at = now() - interval '10 minutes'")
    assert first_item(web)["applicant"]["follow_up"]["new_call_since"] is False


def test_never_followed_up_means_no_marker_even_with_calls(web):
    add_call(minutes_ago=5)
    assert first_item(web)["applicant"]["follow_up"]["new_call_since"] is False


def test_setting_a_status_clears_the_marker(web):
    add_call(minutes_ago=5)
    q("UPDATE applicants SET follow_up_updated_at = now() - interval '10 minutes'")
    assert first_item(web)["applicant"]["follow_up"]["new_call_since"] is True
    set_follow_up(web, applicant_id(), status="called")
    assert first_item(web)["applicant"]["follow_up"]["new_call_since"] is False


# --- filter ---------------------------------------------------------------------------------

def test_filter_calls_by_follow_up_status(web):
    add_call("A", "+12065550101")
    done_call = add_call("B", "+12065550102")
    q("UPDATE applicants SET follow_up_status = 'done' WHERE phone_e164 = '+12065550102'")
    body = web.get("/api/calls?follow_up=done").json()
    assert [i["id"] for i in body["items"]] == [done_call] and body["total"] == 1


def test_unknown_follow_up_filter_is_rejected(web):
    assert web.get("/api/calls?follow_up=banana").status_code == 422
