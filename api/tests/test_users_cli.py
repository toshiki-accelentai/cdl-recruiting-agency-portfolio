"""Creating, listing and rotating dashboard logins from the command line. Written before the code.

The rule that matters: a password is never printed. It goes into a file only the owner can read
(or comes from a file), so it cannot end up in the chat, a log, shell history or git.
"""
import os
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.users_cli import main
from tests.conftest import TEST_URL


def login(username, password):
    from app.main import app
    return TestClient(app).post("/login", data={"username": username, "password": password})


def rows(db):
    return db.execute("SELECT username, role, session_version FROM users ORDER BY username").fetchall()


@pytest.fixture
def run(clean_tables, capsys):
    def go(*argv):
        code = main(list(argv))
        captured = capsys.readouterr()
        return code, captured.out + captured.err
    return go


# --- create -----------------------------------------------------------------------------------

def test_create_generates_a_password_into_a_file_and_never_prints_it(run, db, tmp_path):
    target = tmp_path / "demo.password"
    code, output = run("create", "demo", "recruiter", "--write-password-to", str(target))
    assert code == 0
    password = target.read_text(encoding="utf-8").strip()
    assert len(password) >= 16
    assert password not in output and str(target) in output  # the file is named, the secret is not
    assert rows(db) == [("demo", "recruiter", 1)]
    assert login("demo", password).status_code == 200


@pytest.mark.skipif(os.name == "nt", reason="file modes are not enforced on Windows")
def test_the_password_file_is_readable_by_the_owner_only(run, tmp_path):
    target = tmp_path / "admin.password"
    run("create", "owner", "admin", "--write-password-to", str(target))
    assert (target.stat().st_mode & 0o777) == 0o600


def test_create_with_a_password_from_a_file(run, db, tmp_path):
    source = tmp_path / "chosen.txt"
    source.write_text("a-long-chosen-password\n", encoding="utf-8")
    code, output = run("create", "demo", "recruiter", "--password-file", str(source))
    assert code == 0 and "a-long-chosen-password" not in output
    assert login("demo", "a-long-chosen-password").status_code == 200


def test_a_short_chosen_password_is_refused(run, db, tmp_path):
    source = tmp_path / "short.txt"
    source.write_text("short\n", encoding="utf-8")
    code, output = run("create", "demo", "recruiter", "--password-file", str(source))
    assert code == 1 and "at least 12" in output
    assert rows(db) == []


def test_without_a_password_source_nothing_is_created(run, db):
    code, output = run("create", "demo", "recruiter")
    assert code == 1 and "--write-password-to" in output
    assert rows(db) == []


def test_an_existing_username_is_left_alone(run, db, tmp_path):
    run("create", "demo", "recruiter", "--write-password-to", str(tmp_path / "first.password"))
    code, output = run("create", "demo", "admin", "--write-password-to", str(tmp_path / "second.password"))
    assert code == 1 and "already exists" in output
    assert rows(db) == [("demo", "recruiter", 1)]
    assert not (tmp_path / "second.password").exists()  # no stray password for a user that was not created


def test_an_existing_password_file_is_never_overwritten(run, db, tmp_path):
    target = tmp_path / "keep.password"
    target.write_text("do-not-lose-me", encoding="utf-8")
    code, output = run("create", "demo", "recruiter", "--write-password-to", str(target))
    assert code == 1 and "already exists" in output
    assert target.read_text(encoding="utf-8") == "do-not-lose-me"
    assert rows(db) == []


def test_only_the_two_known_roles_are_accepted(run, db, tmp_path):
    with pytest.raises(SystemExit):
        main(["create", "demo", "superuser", "--write-password-to", str(tmp_path / "x.password")])
    assert rows(db) == []


# --- rotate -----------------------------------------------------------------------------------

def test_rotate_changes_the_password_and_logs_everyone_out(run, db, tmp_path):
    first = tmp_path / "first.password"
    run("create", "demo", "recruiter", "--write-password-to", str(first))
    old = first.read_text(encoding="utf-8").strip()
    from app.main import app
    browser = TestClient(app)
    assert browser.post("/login", data={"username": "demo", "password": old}).status_code == 200
    assert browser.get("/api/me").status_code == 200

    second = tmp_path / "second.password"
    code, output = run("rotate", "demo", "--write-password-to", str(second))
    new = second.read_text(encoding="utf-8").strip()
    assert code == 0 and new != old and new not in output and old not in output
    assert login("demo", new).status_code == 200 and login("demo", old).status_code == 401
    assert browser.get("/api/me").status_code == 401  # the old session cookie stopped working
    assert rows(db) == [("demo", "recruiter", 2)]


def test_rotate_an_unknown_user_changes_nothing(run, db, tmp_path):
    target = tmp_path / "x.password"
    code, output = run("rotate", "ghost", "--write-password-to", str(target))
    assert code == 1 and "no such user" in output and not target.exists()


# --- list -------------------------------------------------------------------------------------

def test_list_shows_names_and_roles_but_never_hashes(run, db, tmp_path):
    run("create", "demo", "recruiter", "--write-password-to", str(tmp_path / "a.password"))
    run("create", "owner", "admin", "--write-password-to", str(tmp_path / "b.password"))
    code, output = run("list")
    assert code == 0 and "demo" in output and "recruiter" in output and "owner" in output and "admin" in output
    stored = db.execute("SELECT password_hash FROM users WHERE username = 'demo'").fetchone()[0]
    assert stored not in output and "argon2" not in output


# --- connecting to a database from a file ------------------------------------------------------

def test_the_database_address_can_come_from_an_env_file_and_is_never_printed(run, db, tmp_path, monkeypatch):
    env_file = tmp_path / "db.env"
    env_file.write_text(f'OTHER=1\nDATABASE_URL="{TEST_URL}"\n', encoding="utf-8")
    monkeypatch.setenv("DATABASE_URL", "postgresql://nobody:wrong@localhost:1/none")  # would fail if used
    code, output = run("list", "--env-file", str(env_file))
    assert code == 0 and TEST_URL not in output and "nobody" not in output


def test_a_missing_env_file_is_a_clear_error(run, tmp_path):
    code, output = run("list", "--env-file", str(tmp_path / "missing.env"))
    assert code == 1 and "env file" in output
