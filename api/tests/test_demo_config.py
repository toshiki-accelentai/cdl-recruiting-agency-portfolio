"""C4 Part A step 1: the demo server runs with only DATABASE_URL and SESSION_SECRET.

No API_SHARED_SECRET (n8n cannot post), no VAPI_PRIVATE_KEY (no recordings from VAPI). Pages and reads still work;
every door that would need a missing key answers 503 and never reaches the outside. Written before any C4 code.
"""
import psycopg
import pytest

from app import recordings
from tests.conftest import TEST_API_KEY, TEST_URL
from tests.test_calls_api import add_call, web  # noqa: F401  (web is a pytest fixture)


@pytest.fixture
def demo_env(monkeypatch):
    monkeypatch.delenv("API_SHARED_SECRET", raising=False)
    monkeypatch.delenv("VAPI_PRIVATE_KEY", raising=False)

    def no_network(url, key):
        raise AssertionError("the demo server must never call VAPI")
    monkeypatch.setattr(recordings, "_open_without_redirect", no_network)


def test_pages_and_reads_work_without_the_n8n_and_vapi_keys(demo_env, web):
    call_id = add_call()
    with psycopg.connect(TEST_URL) as conn:
        applicant_id = conn.execute("SELECT applicant_id FROM calls WHERE id = %s", (call_id,)).fetchone()[0]
    for path in ("/", f"/applicants/{applicant_id}", "/api/todo", "/api/calls", f"/api/calls/{call_id}",
                 f"/api/applicants/{applicant_id}"):
        assert web.get(path, follow_redirects=False).status_code == 200, path


def test_n8n_doors_answer_503_even_with_a_guessed_key(demo_env, web, payload):
    headers = {"X-API-Key": TEST_API_KEY}
    assert web.post("/calls", json=payload, headers=headers).status_code == 503
    report = {"message": {"type": "end-of-call-report", "call": {"id": "demo-call-1"}}}
    assert web.post("/call-reports", json=report, headers=headers).status_code == 503


def test_nothing_is_saved_when_n8n_doors_are_closed(demo_env, web, payload):
    web.post("/calls", json=payload, headers={"X-API-Key": TEST_API_KEY})
    with psycopg.connect(TEST_URL) as conn:
        assert conn.execute("SELECT count(*) FROM calls").fetchone()[0] == 0


def test_recording_without_a_vapi_key_is_503_and_vapi_is_not_called(demo_env, web):
    call_id = add_call(vapi_id="vapi-demo-1")
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        conn.execute("UPDATE calls SET has_recording = true WHERE id = %s", (call_id,))
    assert web.get(f"/api/calls/{call_id}/recording", follow_redirects=False).status_code == 503
