"""Cleanup tool: remove one dashboard login (owner request 2026-10-26: the old `demo` recruiter login on the real instance).

scripts/delete_user.py runs inside the API container over ssh. It is a dry run unless told to --apply. It removes ONE
recruiter login, by exact username, and refuses anything that would be hard to undo: an admin, an unknown name, or a
login that has change-history rows (the history table is never deleted from). Written before the code.
"""
import importlib.util
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.auth import create_user
from tests.conftest import TEST_URL

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "delete_user.py"
PASSWORD = "a-long-test-password-1234"


def tool():
    spec = importlib.util.spec_from_file_location("delete_user", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(username, apply=False):
    with psycopg.connect(TEST_URL) as conn:
        return tool().run(conn, username, apply)


def usernames():
    with psycopg.connect(TEST_URL) as conn:
        return [r[0] for r in conn.execute("SELECT username FROM users ORDER BY username")]


@pytest.fixture
def logins(clean_tables):
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        for name, role in (("owner", "admin"), ("demo", "recruiter"), ("demo2", "recruiter")):
            create_user(conn, name, PASSWORD, role)


def session_for(username):
    from app.main import app
    client = TestClient(app)
    assert client.post("/login", data={"username": username, "password": PASSWORD}).status_code == 200
    return client


# --- dry run ----------------------------------------------------------------------------------------------

def test_a_dry_run_reports_the_login_and_deletes_nothing(logins):
    result = run("demo")
    assert result["applied"] is False
    assert result["username"] == "demo" and result["role"] == "recruiter" and result["history_rows"] == 0
    assert usernames() == ["demo", "demo2", "owner"]


def test_the_report_never_contains_the_password_hash(logins):
    assert "argon2" not in str(run("demo")) and "password" not in " ".join(run("demo"))


# --- apply ------------------------------------------------------------------------------------------------

def test_apply_removes_exactly_that_login_and_no_other(logins):
    assert run("demo", apply=True)["applied"] is True
    assert usernames() == ["demo2", "owner"]


def test_a_removed_login_can_no_longer_sign_in_and_an_open_session_stops_working(logins):
    signed_in = session_for("demo")
    assert signed_in.get("/api/todo").status_code == 200
    run("demo", apply=True)
    assert signed_in.get("/api/todo").status_code == 401
    from app.main import app
    assert TestClient(app).post("/login", data={"username": "demo", "password": PASSWORD}).status_code == 401


def test_the_owner_session_is_untouched(logins):
    owner = session_for("owner")
    run("demo", apply=True)
    assert owner.get("/api/todo").status_code == 200


# --- refusals ---------------------------------------------------------------------------------------------

def test_an_admin_login_is_refused(logins):
    with pytest.raises(ValueError, match="recruiter"):
        run("owner", apply=True)
    assert "owner" in usernames()


def test_an_unknown_name_is_refused(logins):
    with pytest.raises(ValueError, match="no login"):
        run("nobody", apply=True)


@pytest.mark.parametrize("pattern", ["dem%", "dem_", "%", "DEMO", " demo", ""])
def test_only_an_exact_username_matches(logins, pattern):
    with pytest.raises(ValueError):
        run(pattern, apply=True)
    assert usernames() == ["demo", "demo2", "owner"]


def test_a_login_with_change_history_is_refused_and_nothing_is_deleted(logins):
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        user_id = conn.execute("SELECT id FROM users WHERE username = 'demo'").fetchone()[0]
        conn.execute("INSERT INTO audit_log (user_id, action, changes) VALUES (%s, 'correct_applicant', '{}')", (user_id,))
    with pytest.raises(ValueError, match="history"):
        run("demo", apply=True)
    assert "demo" in usernames()
    with psycopg.connect(TEST_URL) as conn:
        assert conn.execute("SELECT count(*) FROM audit_log").fetchone()[0] == 1


def test_a_dry_run_also_refuses_so_the_owner_sees_the_problem_before_applying(logins):
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        user_id = conn.execute("SELECT id FROM users WHERE username = 'demo'").fetchone()[0]
        conn.execute("INSERT INTO audit_log (user_id, action, changes) VALUES (%s, 'correct_applicant', '{}')", (user_id,))
    with pytest.raises(ValueError, match="history"):
        run("demo", apply=False)


# --- the command line -------------------------------------------------------------------------------------

def test_main_prints_dry_run_then_removed_and_returns_codes(logins, capsys, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", TEST_URL)
    module = tool()
    assert module.main(["demo"]) == 0
    assert "DRY RUN, nothing removed" in capsys.readouterr().out
    assert module.main(["demo", "--apply"]) == 0
    assert "REMOVED" in capsys.readouterr().out
    assert module.main(["owner", "--apply"]) == 1
    assert "refused" in capsys.readouterr().out
    assert module.main([]) == 2
    assert usernames() == ["demo2", "owner"]
