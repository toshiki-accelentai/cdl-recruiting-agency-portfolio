"""Independent review, first batch of fixes (docs/SECURITY-REVIEW.md, 2026-10-22). Written before the code.

 N2  a weak session secret is refused, and each instance (demo, real) signs its cookies differently
 N3  python-multipart has a floor that excludes the versions with the known multipart DoS
 F2  the password is hashed after the database connection is handed back; a pool timeout is a clean 503
 F5  the write limit is per (user, client address), so one demo visitor cannot use up everyone's quota
 N8  a server running with DEMO_MODE=1 refuses to start if it holds the n8n key or the VAPI key
"""
import re
from contextlib import contextmanager
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg_pool import PoolTimeout

from tests.conftest import TEST_URL
from tests.test_calls_api import PASSWORD, add_call, web  # noqa: F401  (web is a pytest fixture)

REQUIREMENTS = Path(__file__).resolve().parents[1] / "requirements.txt"


class SpyHasher:
    """Stands in for auth.hasher (argon2's PasswordHasher cannot be patched in place) and records each verify."""

    def __init__(self, real, on_verify):
        self._real, self._on_verify = real, on_verify

    def verify(self, *args, **kwargs):
        self._on_verify()
        return self._real.verify(*args, **kwargs)

    def hash(self, *args, **kwargs):
        return self._real.hash(*args, **kwargs)


def login(client):
    return client.post("/login", data={"username": "demo", "password": PASSWORD})


# --- N2 ----------------------------------------------------------------------------------------

def test_a_short_session_secret_is_treated_as_not_configured(clean_tables, monkeypatch):
    from app.main import app
    monkeypatch.setenv("SESSION_SECRET", "too-short")
    assert login(TestClient(app)).status_code == 503


def test_a_cookie_from_another_instance_is_not_accepted(web, monkeypatch):
    assert web.get("/api/todo").status_code == 200  # signed with no instance name
    monkeypatch.setenv("INSTANCE_NAME", "real")
    assert web.get("/api/todo").status_code == 401  # the same secret, another instance: rejected


def test_the_same_instance_name_keeps_its_cookies_valid(clean_tables, monkeypatch):
    from app.auth import create_user
    from app.main import app
    monkeypatch.setenv("INSTANCE_NAME", "demo")
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        create_user(conn, "demo", PASSWORD, "recruiter")
    client = TestClient(app)
    assert login(client).status_code == 200
    assert client.get("/api/todo").status_code == 200


# --- N3 ----------------------------------------------------------------------------------------

def test_python_multipart_floor_excludes_the_vulnerable_versions():
    line = next(l for l in REQUIREMENTS.read_text(encoding="utf-8").splitlines() if l.startswith("python-multipart"))
    floor = tuple(int(n) for n in re.search(r">=\s*([\d.]+)", line).group(1).split("."))
    assert floor >= (0, 0, 18)


# --- F2 ----------------------------------------------------------------------------------------

def test_the_password_is_hashed_without_holding_a_database_connection(web, monkeypatch):
    from app import auth
    open_now, seen = [0], []
    original = auth.db_connection

    @contextmanager
    def counting():
        open_now[0] += 1
        try:
            with original() as conn:
                yield conn
        finally:
            open_now[0] -= 1

    monkeypatch.setattr(auth, "db_connection", counting)
    monkeypatch.setattr(auth, "hasher", SpyHasher(auth.hasher, lambda: seen.append(open_now[0])))
    assert login(web).status_code == 200
    assert seen == [0]


def test_a_wrong_password_and_an_unknown_user_still_answer_401_and_both_are_hashed(web, monkeypatch):
    from app import auth
    seen = []
    monkeypatch.setattr(auth, "hasher", SpyHasher(auth.hasher, lambda: seen.append(1)))
    assert web.post("/login", data={"username": "demo", "password": "wrong-password-1"}).status_code == 401
    assert web.post("/login", data={"username": "nobody", "password": "wrong-password-1"}).status_code == 401
    assert len(seen) == 2  # an unknown user costs the same as a wrong password


def test_a_pool_timeout_is_a_clean_503_with_retry_after(web, monkeypatch):
    from app import todo

    @contextmanager
    def exhausted():
        raise PoolTimeout("couldn't get a connection")
        yield

    monkeypatch.setattr(todo, "db_connection", exhausted)
    r = web.get("/api/todo")
    assert r.status_code == 503 and int(r.headers["Retry-After"]) >= 1


# --- F5 ----------------------------------------------------------------------------------------

def test_the_write_limit_is_per_user_and_client_address(web):
    from app.throttle import MAX_WRITES
    add_call(name="Marcus Hill", phone="+13125550148", vapi_id="f5")
    with psycopg.connect(TEST_URL) as conn:
        applicant_id = conn.execute("SELECT id FROM applicants").fetchone()[0]

    def patch(ip):
        return web.patch(f"/api/applicants/{applicant_id}/follow-up", json={"status": "called"},
                         headers={"X-Forwarded-For": ip})

    assert [patch("198.51.100.1").status_code for _ in range(MAX_WRITES)] == [200] * MAX_WRITES
    assert patch("198.51.100.1").status_code == 429
    assert patch("198.51.100.2").status_code == 200  # another visitor on the same shared login


# --- N8 ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("key", ["API_SHARED_SECRET", "VAPI_PRIVATE_KEY"])
def test_a_demo_server_refuses_to_start_with_the_n8n_or_vapi_key(clean_tables, monkeypatch, key):
    from app.main import app
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv(key, "something-secret")
    with pytest.raises(RuntimeError, match="DEMO_MODE"):
        with TestClient(app):
            pass


def test_a_demo_server_without_those_keys_starts(clean_tables, monkeypatch):
    from app.main import app
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.delenv("API_SHARED_SECRET", raising=False)
    monkeypatch.delenv("VAPI_PRIVATE_KEY", raising=False)
    with TestClient(app) as client:
        assert client.get("/login").status_code == 200


def test_the_real_server_is_not_affected(clean_tables, monkeypatch):
    from app.main import app
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.setenv("VAPI_PRIVATE_KEY", "something-secret")
    with TestClient(app) as client:
        assert client.get("/login").status_code == 200
