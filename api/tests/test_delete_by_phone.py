"""One-off cleanup tool: remove the records that belong to one phone number (the owner's own, used for test calls).

scripts/delete_by_phone.py runs inside the API container over ssh. It shows what it would delete (a dry run) unless it
is told to --apply, matches by the last 4 digits, and refuses a suffix that matches more than a few people.
Written before the code.
"""
import importlib.util
from pathlib import Path

import psycopg
import pytest

from tests.conftest import TEST_URL
from tests.test_calls_api import add_call

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "delete_by_phone.py"
MINE, OTHER = "+16725554656", "+12065550160"


def tool():
    spec = importlib.util.spec_from_file_location("delete_by_phone", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(last4, apply=False):
    with psycopg.connect(TEST_URL) as conn:
        return tool().run(conn, last4, apply)


def count(sql):
    with psycopg.connect(TEST_URL) as conn:
        return conn.execute(sql).fetchone()[0]


def seed_two_people():
    add_call(name="John Smith", phone=MINE, outbox={"status": "sent"}, vapi_id="mine-1", minutes_ago=30)
    add_call(name="John Smith", phone=MINE, outbox={"status": "sent"}, vapi_id="mine-2", minutes_ago=10)
    add_call(name="Test Driver", phone=OTHER, outbox={"status": "sent"}, vapi_id="other-1")
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        user_id = conn.execute("INSERT INTO users (username, password_hash, role) VALUES ('u', 'x', 'admin') "
                               "RETURNING id").fetchone()[0]
        for phone in (MINE, OTHER):
            conn.execute("INSERT INTO audit_log (user_id, action, applicant_id, changes) "
                         "SELECT %s, 'update_follow_up', id, '{}' FROM applicants WHERE phone_e164 = %s", (user_id, phone))
        conn.execute("INSERT INTO calls (vapi_call_id, raw_payload, caller_number, needs_review, review_reason) "
                     "VALUES ('mine-unlinked', '{}', %s, true, 'no_intake')", (MINE,))


def test_a_dry_run_reports_and_deletes_nothing(clean_tables):
    seed_two_people()
    result = run("4656")
    assert result == {"applicants": 1, "calls": 3, "outbox": 2, "audit_log": 1, "applied": False}
    assert count("SELECT count(*) FROM applicants") == 2
    assert count("SELECT count(*) FROM calls") == 4


def test_apply_removes_that_person_and_nothing_else(clean_tables):
    seed_two_people()
    result = run("4656", apply=True)
    assert result["applied"] is True and result["applicants"] == 1 and result["calls"] == 3
    assert count("SELECT count(*) FROM applicants WHERE phone_e164 = '+16725554656'") == 0
    assert count("SELECT count(*) FROM calls WHERE caller_number = '+16725554656'") == 0
    assert count("SELECT count(*) FROM applicants WHERE phone_e164 = '+12065550160'") == 1
    assert count("SELECT count(*) FROM calls") == 1 and count("SELECT count(*) FROM outbox") == 1
    assert count("SELECT count(*) FROM audit_log") == 1
    assert count("SELECT count(*) FROM users") == 1  # logins are never touched


def test_nothing_matching_is_not_an_error(clean_tables):
    seed_two_people()
    assert run("9999", apply=True) == {"applicants": 0, "calls": 0, "outbox": 0, "audit_log": 0, "applied": True}
    assert count("SELECT count(*) FROM applicants") == 2


@pytest.mark.parametrize("bad", ["", "465", "46567", "abcd", "+1672"])
def test_only_exactly_four_digits_are_accepted(clean_tables, bad):
    with pytest.raises(ValueError):
        run(bad, apply=True)


def test_refuses_a_suffix_that_matches_too_many_people(clean_tables):
    for i in range(4):
        add_call(name=f"P{i}", phone=f"+120{i}5550999", vapi_id=f"v{i}")
    with pytest.raises(ValueError):
        run("0999", apply=True)
    assert count("SELECT count(*) FROM applicants") == 4
