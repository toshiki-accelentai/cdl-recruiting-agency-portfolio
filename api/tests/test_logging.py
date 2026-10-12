"""What the API and worker write to the log. Phone numbers must never appear in it."""
import logging

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import main
from app.db import connect_with_retry
from app.zoho import ZohoError
from tests.conftest import TEST_API_KEY
from tests.test_connect_retry import FlakyConnect
from tests.test_worker import FakeZoho, conn, make_due, post_call  # noqa: F401 (conn is a fixture)

PHONE_DIGITS = "2065550142"


@pytest.fixture(autouse=True)
def info_logs(caplog):
    caplog.set_level(logging.INFO, logger="app")


def lines(caplog):
    return [r.getMessage() for r in caplog.records]


def test_api_logs_a_saved_call_by_id_only(client, payload, caplog):
    assert client.post("/calls", json=payload).status_code == 201
    assert "call saved call_id=1 applicant_id=1 needs_review=False" in lines(caplog)
    assert "6727274656" not in caplog.text and "John" not in caplog.text


def test_api_logs_a_replayed_call_as_duplicate(client, payload, caplog):
    client.post("/calls", json=payload)
    caplog.clear()
    assert client.post("/calls", json=payload).status_code == 200
    assert "duplicate call call_id=1" in lines(caplog)


def test_api_logs_a_flagged_call(client, payload, caplog):
    payload["message"]["toolCalls"][0]["function"]["arguments"]["phoneNumber"] = "672 727"
    client.post("/calls", json=payload)
    assert any("needs_review=True" in line for line in lines(caplog))


def test_api_logs_an_error_when_the_database_save_fails(payload, caplog, monkeypatch):
    def down(url):
        raise psycopg.OperationalError("failed to resolve host 'db.example'")
    monkeypatch.setattr(main, "connect_with_retry", down)
    r = TestClient(main.app, raise_server_exceptions=False,
                   headers={"X-API-Key": TEST_API_KEY}).post("/calls", json=payload)
    assert r.status_code == 500  # n8n sees the failure and takes the "not saved" path
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert any("save failed" in r.getMessage() and "OperationalError" in r.getMessage()
               and "failed to resolve host" in r.getMessage() for r in errors)


def test_each_failed_connect_try_is_logged_as_a_warning(caplog):
    connect_with_retry("url", connect=FlakyConnect(2), sleep=lambda s: None)
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 2
    assert "try 1/3" in warnings[0] and "try 2/3" in warnings[1]
    assert "failed to resolve host" in warnings[0]


def test_worker_logs_a_sent_row(client, payload, conn, zoho_ok, caplog):
    post_call(client, payload, "call-1", PHONE_DIGITS)
    caplog.clear()
    assert worker_process(conn, zoho_ok) == "sent"
    assert "outbox id=1 sent attempt=1" in lines(caplog)
    assert PHONE_DIGITS not in caplog.text


def test_worker_logs_a_retry_with_attempt_and_wait(client, payload, db, conn, zoho_ok, caplog):
    post_call(client, payload, "call-1", PHONE_DIGITS)
    zoho_ok.fail_with = ZohoError("retry", "network error: zoho-down.invalid")
    caplog.clear()
    assert worker_process(conn, zoho_ok) == "retry"
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("outbox id=1 retry attempt=1 next_in=30s" in w and "network error" in w
               for w in warnings)
    make_due(db)
    caplog.clear()
    worker_process(conn, zoho_ok)
    assert any("attempt=2 next_in=60s" in r.getMessage() for r in caplog.records)


def test_worker_logs_a_permanent_failure_as_error(client, payload, conn, zoho_ok, caplog):
    post_call(client, payload, "call-1", PHONE_DIGITS)
    zoho_ok.fail_with = ZohoError("fail", "Zoho HTTP 400: bad field")
    caplog.clear()
    assert worker_process(conn, zoho_ok) == "failed"
    errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert any("outbox id=1 failed attempt=1" in e and "bad field" in e for e in errors)


def test_worker_error_text_in_the_log_is_cut_short(client, payload, conn, zoho_ok, caplog):
    post_call(client, payload, "call-1", PHONE_DIGITS)
    zoho_ok.fail_with = ZohoError("retry", "x" * 1000)
    caplog.clear()
    worker_process(conn, zoho_ok)
    assert "x" * 200 not in caplog.text


@pytest.fixture
def zoho_ok():
    return FakeZoho()


def worker_process(conn, zoho):
    from app import worker
    return worker.process_one(conn, zoho)
