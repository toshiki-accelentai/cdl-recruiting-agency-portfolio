"""C1e: GET /api/calls/{id}/recording sends a logged-in recruiter to a fresh, short-lived signed link.

The stored link in VAPI's data is a private bucket address that does not play; the signed link comes
from VAPI's API using the private key, which stays on the server. Written before the code.
"""
import io
import urllib.error

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import recordings
from tests.conftest import TEST_API_KEY, TEST_URL
from tests.test_calls_api import add_call, web  # noqa: F401  (web is a pytest fixture)

SIGNED = "https://bucket.example.invalid/rec.wav?X-Amz-Expires=1800&X-Amz-Signature=abc"


def set_recording(call_id, has_recording=True):
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        conn.execute("UPDATE calls SET has_recording = %s WHERE id = %s", (has_recording, call_id))


@pytest.fixture
def signed_link(monkeypatch):
    seen = []
    monkeypatch.setattr(recordings, "signed_recording_url", lambda vapi_call_id: seen.append(vapi_call_id) or SIGNED)
    return seen


# --- the endpoint ------------------------------------------------------------------------------

def test_recording_needs_a_login(clean_tables):
    from app.main import app
    call_id = add_call()
    set_recording(call_id)
    assert TestClient(app).get(f"/api/calls/{call_id}/recording").status_code == 401
    assert TestClient(app, headers={"X-API-Key": TEST_API_KEY}).get(f"/api/calls/{call_id}/recording").status_code == 401


def test_unknown_call_is_404(web, signed_link):
    assert web.get("/api/calls/999999/recording", follow_redirects=False).status_code == 404


def test_call_without_a_recording_is_404_and_vapi_is_not_asked(web, signed_link):
    call_id = add_call()  # has_recording defaults to false
    assert web.get(f"/api/calls/{call_id}/recording", follow_redirects=False).status_code == 404
    assert signed_link == []


def test_redirects_to_the_signed_link_without_caching(web, signed_link):
    call_id = add_call(vapi_id="vapi-abc-123")
    set_recording(call_id)
    r = web.get(f"/api/calls/{call_id}/recording", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == SIGNED
    assert r.headers["cache-control"] == "no-store"
    assert signed_link == ["vapi-abc-123"]


def test_vapi_says_no_recording_is_404(web, monkeypatch):
    monkeypatch.setattr(recordings, "signed_recording_url", lambda _id: None)
    call_id = add_call()
    set_recording(call_id)
    assert web.get(f"/api/calls/{call_id}/recording", follow_redirects=False).status_code == 404


def test_vapi_failure_is_502(web, monkeypatch):
    def boom(_id):
        raise recordings.VapiError("vapi answered 500")
    monkeypatch.setattr(recordings, "signed_recording_url", boom)
    call_id = add_call()
    set_recording(call_id)
    assert web.get(f"/api/calls/{call_id}/recording", follow_redirects=False).status_code == 502


def test_missing_vapi_key_is_503(web, monkeypatch):
    def not_configured(_id):
        raise recordings.NotConfigured("VAPI_PRIVATE_KEY is not set")
    monkeypatch.setattr(recordings, "signed_recording_url", not_configured)
    call_id = add_call()
    set_recording(call_id)
    assert web.get(f"/api/calls/{call_id}/recording", follow_redirects=False).status_code == 503


# --- the VAPI helper, with the network call replaced ---------------------------------------------

def redirect_error(location, status=302):
    return urllib.error.HTTPError("https://api.vapi.ai/x", status, "Found", {"Location": location}, io.BytesIO(b""))


def http_error(status):
    return urllib.error.HTTPError("https://api.vapi.ai/x", status, "err", {}, io.BytesIO(b""))


@pytest.fixture
def vapi_key(monkeypatch):
    monkeypatch.setenv("VAPI_PRIVATE_KEY", "test-vapi-key")


def test_helper_asks_vapi_with_the_key_and_returns_the_location(vapi_key, monkeypatch):
    calls = []

    def fake_open(url, key):
        calls.append((url, key))
        raise redirect_error(SIGNED)

    monkeypatch.setattr(recordings, "_open_without_redirect", fake_open)
    assert recordings.signed_recording_url("0193-abc") == SIGNED
    assert calls == [("https://api.vapi.ai/call/0193-abc/mono-recording", "test-vapi-key")]


def test_helper_returns_none_when_vapi_has_no_recording(vapi_key, monkeypatch):
    monkeypatch.setattr(recordings, "_open_without_redirect", lambda url, key: (_ for _ in ()).throw(http_error(404)))
    assert recordings.signed_recording_url("0193-abc") is None


def test_helper_raises_on_other_vapi_errors(vapi_key, monkeypatch):
    monkeypatch.setattr(recordings, "_open_without_redirect", lambda url, key: (_ for _ in ()).throw(http_error(500)))
    with pytest.raises(recordings.VapiError):
        recordings.signed_recording_url("0193-abc")


def test_helper_raises_when_vapi_does_not_redirect(vapi_key, monkeypatch):
    class Ok:
        pass
    monkeypatch.setattr(recordings, "_open_without_redirect", lambda url, key: Ok())
    with pytest.raises(recordings.VapiError):
        recordings.signed_recording_url("0193-abc")


def test_helper_only_follows_https_links(vapi_key, monkeypatch):
    monkeypatch.setattr(recordings, "_open_without_redirect",
                        lambda url, key: (_ for _ in ()).throw(redirect_error("http://evil.invalid/x")))
    with pytest.raises(recordings.VapiError):
        recordings.signed_recording_url("0193-abc")


def test_helper_without_a_key_raises_not_configured(monkeypatch):
    monkeypatch.delenv("VAPI_PRIVATE_KEY", raising=False)
    with pytest.raises(recordings.NotConfigured):
        recordings.signed_recording_url("0193-abc")


@pytest.mark.parametrize("bad_id", ["", "../x", "a/b", "id with space", "x" * 100, "a?b=c"])
def test_helper_refuses_ids_that_are_not_plain_call_ids(vapi_key, bad_id):
    with pytest.raises(ValueError):
        recordings.signed_recording_url(bad_id)
