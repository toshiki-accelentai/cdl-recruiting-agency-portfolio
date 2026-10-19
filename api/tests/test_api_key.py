"""POST /calls needs the shared secret in the X-API-Key header. Nothing may be saved without it."""
import logging

import pytest
from fastapi.testclient import TestClient

from app import main
from tests.conftest import TEST_API_KEY


@pytest.fixture
def anonymous(clean_tables):
    """A client that sends no key."""
    return TestClient(main.app)


def count_calls(db):
    return db.execute("SELECT count(*) FROM calls").fetchone()[0]


def test_missing_key_is_rejected_and_nothing_is_saved(anonymous, payload, db):
    assert anonymous.post("/calls", json=payload).status_code == 401
    assert count_calls(db) == 0


def test_wrong_key_is_rejected_and_nothing_is_saved(anonymous, payload, db):
    r = anonymous.post("/calls", json=payload, headers={"X-API-Key": "not-the-secret"})
    assert r.status_code == 401
    assert count_calls(db) == 0


def test_key_that_only_starts_like_the_secret_is_rejected(anonymous, payload):
    r = anonymous.post("/calls", json=payload, headers={"X-API-Key": TEST_API_KEY + "x"})
    assert r.status_code == 401


def test_right_key_is_accepted(anonymous, payload, db):
    r = anonymous.post("/calls", json=payload, headers={"X-API-Key": TEST_API_KEY})
    assert r.status_code == 201
    assert count_calls(db) == 1


def test_key_is_checked_before_the_body(anonymous):
    # An empty body would be a 422; a caller without the key must not learn anything about the body.
    assert anonymous.post("/calls", json={}).status_code == 401


def test_server_without_a_configured_secret_refuses_everything(anonymous, payload, db, monkeypatch):
    monkeypatch.delenv("API_SHARED_SECRET")
    r = anonymous.post("/calls", json=payload, headers={"X-API-Key": TEST_API_KEY})
    assert r.status_code == 503  # server misconfigured: never "open by default"
    assert count_calls(db) == 0


def test_empty_secret_setting_also_refuses_everything(anonymous, payload, monkeypatch):
    monkeypatch.setenv("API_SHARED_SECRET", "")
    r = anonymous.post("/calls", json=payload, headers={"X-API-Key": ""})
    assert r.status_code == 503


def test_healthz_stays_open_for_the_docker_healthcheck(anonymous):
    assert anonymous.get("/healthz").status_code == 200


def test_rejected_request_is_logged_without_the_key(anonymous, payload, caplog):
    caplog.set_level(logging.INFO, logger="app")
    anonymous.post("/calls", json=payload, headers={"X-API-Key": "guess-12345"})
    assert any("rejected" in r.getMessage() and r.levelno == logging.WARNING for r in caplog.records)
    assert "guess-12345" not in caplog.text and TEST_API_KEY not in caplog.text
