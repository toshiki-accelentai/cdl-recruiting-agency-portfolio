"""C1a: login, signed session cookie, roles. Written before the code (RED first)."""
import os

import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.conftest import TEST_URL

PASSWORD = "correct horse battery"


def make_user(username="demo", role="recruiter", password=PASSWORD):
    from app.auth import create_user
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        return create_user(conn, username, password, role)


@pytest.fixture
def web():
    """A browser-like client: keeps cookies, sends NO X-API-Key (that key is only for n8n)."""
    from app.main import app
    return TestClient(app)


def login(web, username="demo", password=PASSWORD):
    return web.post("/login", data={"username": username, "password": password})


def test_me_without_login_is_401(clean_tables, web):
    assert web.get("/api/me").status_code == 401


def test_login_with_right_password_opens_the_session(clean_tables, web):
    make_user("demo", "recruiter")
    resp = login(web)
    assert resp.status_code == 200
    assert web.get("/api/me").json() == {"username": "demo", "role": "recruiter"}


def test_wrong_password_is_401_and_sets_no_cookie(clean_tables, web):
    make_user()
    resp = login(web, password="nope")
    assert resp.status_code == 401
    assert "set-cookie" not in resp.headers
    assert web.get("/api/me").status_code == 401


def test_unknown_user_looks_exactly_like_wrong_password(clean_tables, web):
    make_user()
    wrong_pw = login(web, password="nope")
    unknown = login(web, username="ghost")
    assert unknown.status_code == wrong_pw.status_code == 401
    assert unknown.json() == wrong_pw.json()  # no hint about which usernames exist


def test_password_is_stored_hashed_never_plain(clean_tables):
    make_user()
    with psycopg.connect(TEST_URL) as conn:
        stored = conn.execute("SELECT password_hash FROM users WHERE username = 'demo'").fetchone()[0]
    assert PASSWORD not in stored
    assert stored.startswith("$argon2")


def test_cookie_is_httponly_and_samesite_lax(clean_tables, web):
    make_user()
    header = login(web).headers["set-cookie"].lower()
    assert "httponly" in header
    assert "samesite=lax" in header


def test_cookie_is_secure_unless_local_dev_turns_it_off(clean_tables, web, monkeypatch):
    make_user()
    monkeypatch.delenv("SESSION_COOKIE_SECURE")
    assert "secure" in login(web).headers["set-cookie"].lower()


def test_logout_ends_the_session(clean_tables, web):
    make_user()
    login(web)
    assert web.post("/logout").status_code == 200
    assert web.get("/api/me").status_code == 401


def test_tampered_cookie_is_rejected(clean_tables, web):
    make_user()
    login(web)
    cookie = web.cookies.get("session")
    web.cookies.set("session", cookie[:-3] + ("AAA" if not cookie.endswith("AAA") else "BBB"))
    assert web.get("/api/me").status_code == 401


def test_changing_the_password_logs_everyone_out_at_once(clean_tables, web):
    """The reason for session_version: rotating the demo password must kill sessions already open."""
    from app.auth import change_password
    make_user()
    login(web)
    assert web.get("/api/me").status_code == 200
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        change_password(conn, "demo", "a brand new password")
    assert web.get("/api/me").status_code == 401
    assert login(web, password=PASSWORD).status_code == 401
    assert login(web, password="a brand new password").status_code == 200


def test_login_refuses_to_run_without_a_session_secret(clean_tables, web, monkeypatch):
    """Never open by default: no secret configured -> 503, not a session signed with a blank key."""
    make_user()
    monkeypatch.delenv("SESSION_SECRET")
    assert login(web).status_code == 503


def test_unknown_role_cannot_be_created(clean_tables):
    with pytest.raises(psycopg.errors.CheckViolation):
        make_user(role="superuser")


def test_usernames_are_unique(clean_tables):
    make_user("demo")
    with pytest.raises(psycopg.errors.UniqueViolation):
        make_user("demo")
