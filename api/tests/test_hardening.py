"""C3 step 1: shrink what a stranger can reach before the site goes public. Written before the code.

(a) the API docs are closed   (b) /healthz replaces /docs as the container's health check
(c) the two n8n-only endpoints refuse requests that came through the public proxy
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.test_call_reports import report
from tests.test_calls_api import web  # noqa: F401  (web is a pytest fixture)

COMPOSE = Path(__file__).resolve().parents[1] / "deploy" / "compose.yaml"
PROXY_HEADERS = ["X-Forwarded-For", "X-Forwarded-Host", "X-Forwarded-Proto", "Forwarded", "X-Real-IP"]


@pytest.fixture
def anon(clean_tables):
    from app.main import app
    return TestClient(app)


# --- (a) docs closed ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"])
def test_api_docs_are_closed(anon, path):
    assert anon.get(path).status_code == 404


# --- (b) health check --------------------------------------------------------------------------

def test_healthz_is_public_and_says_ok(anon):
    r = anon.get("/healthz")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_healthz_does_not_touch_the_database(anon, monkeypatch):
    """A health check that needs the database would turn the API 'unhealthy' for every database hiccup."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://nobody:wrong@127.0.0.1:1/none")
    assert anon.get("/healthz").status_code == 200


def test_the_compose_healthcheck_asks_for_healthz_and_never_for_the_closed_docs():
    """Closing /docs while the container still asks for it leaves the API 'unhealthy' and the worker never starts."""
    healthcheck = [line for line in COMPOSE.read_text(encoding="utf-8").splitlines()
                   if "test:" in line and "urlopen" in line]
    assert len(healthcheck) == 1
    assert "/healthz" in healthcheck[0] and "/docs" not in healthcheck[0]


# --- (c) internal-only endpoints ----------------------------------------------------------------

@pytest.mark.parametrize("header", PROXY_HEADERS)
def test_calls_refuses_requests_that_came_through_the_proxy_even_with_the_key(client, payload, db, header):
    r = client.post("/calls", json=payload, headers={header: "203.0.113.9"})
    assert r.status_code == 404
    assert db.execute("SELECT count(*) FROM calls").fetchone()[0] == 0


@pytest.mark.parametrize("header", PROXY_HEADERS)
def test_call_reports_refuses_requests_that_came_through_the_proxy(client, db, header):
    r = client.post("/call-reports", json=report(), headers={header: "203.0.113.9"})
    assert r.status_code == 404
    assert db.execute("SELECT count(*) FROM calls").fetchone()[0] == 0


def test_the_proxy_answer_is_the_same_whether_or_not_the_key_is_right(anon, payload):
    """404 for both: an outsider must not learn that the endpoint exists by getting a 401 instead."""
    no_key = anon.post("/calls", json=payload, headers={"X-Forwarded-For": "203.0.113.9"})
    wrong_key = anon.post("/calls", json=payload,
                          headers={"X-Forwarded-For": "203.0.113.9", "X-API-Key": "nope"})
    assert no_key.status_code == wrong_key.status_code == 404


def test_n8n_inside_path_still_works(client, payload):
    """n8n calls cdl-api directly, so its request has no proxy headers."""
    assert client.post("/calls", json=payload).status_code == 201
    assert client.post("/call-reports", json=report()).status_code == 200


def test_the_dashboard_itself_works_behind_the_proxy(web):
    for path in ("/login", "/api/me"):
        r = web.get(path, headers={"X-Forwarded-For": "203.0.113.9", "X-Forwarded-Proto": "https"})
        assert r.status_code in (200, 401), path  # reachable (401 just means not logged in), not blocked
