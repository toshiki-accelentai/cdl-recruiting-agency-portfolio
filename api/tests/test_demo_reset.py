"""C4 Part A step 3: the nightly reset of the public demo.

It deletes the demo's calls, applicants, outbox rows and change history, then writes the fictional seed again.
It must never touch the real database, so it refuses unless DEMO_MODE=1 AND every row looks like demo data.
Logins (users) are never touched. Written before the code.
"""
import psycopg
import pytest

from tests.conftest import TEST_URL
from tests.test_calls_api import add_call

LOGIN_PASSWORD = "a-long-demo-password"


def run_reset():
    from app import demo_reset
    with psycopg.connect(TEST_URL) as conn:
        demo_reset.reset(conn)


def count(sql):
    with psycopg.connect(TEST_URL) as conn:
        return conn.execute(sql).fetchone()[0]


@pytest.fixture
def demo_mode(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "1")


def seeded():
    from app import demo_seed
    with psycopg.connect(TEST_URL) as conn:
        demo_seed.seed(conn)


# --- the guards --------------------------------------------------------------------------------

def test_refuses_without_demo_mode_and_deletes_nothing(clean_tables, monkeypatch):
    from app.demo_seed import NotDemoMode
    monkeypatch.setenv("DEMO_MODE", "1")
    seeded()
    monkeypatch.delenv("DEMO_MODE")
    with pytest.raises(NotDemoMode):
        run_reset()
    assert count("SELECT count(*) FROM applicants") > 0


def test_refuses_when_a_row_is_not_demo_data(clean_tables, demo_mode):
    """Pointed at the real database by mistake: real calls have no demo marker, so nothing is deleted."""
    from app.demo_reset import NotDemoDatabase
    add_call(name="Real Caller", phone="+12065551234")  # raw_payload without the demo marker
    with pytest.raises(NotDemoDatabase):
        run_reset()
    assert count("SELECT count(*) FROM calls") == 1


def test_refuses_when_an_applicant_has_a_zoho_id(clean_tables, demo_mode):
    from app.demo_reset import NotDemoDatabase
    seeded()
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        conn.execute("UPDATE applicants SET zoho_candidate_id = '870474000000683001' WHERE id = "
                     "(SELECT min(id) FROM applicants)")
    with pytest.raises(NotDemoDatabase):
        run_reset()
    assert count("SELECT count(*) FROM applicants") > 0


# --- the reset ---------------------------------------------------------------------------------

def test_works_on_an_empty_database(clean_tables, demo_mode):
    run_reset()
    assert count("SELECT count(*) FROM applicants") >= 8


def test_removes_a_visitors_edits_and_notes(clean_tables, demo_mode):
    seeded()
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        conn.execute("UPDATE applicants SET name = 'Hacked Name', follow_up_note = 'visitor wrote this'")
        conn.execute("INSERT INTO users (username, password_hash, role) VALUES ('v', 'x', 'recruiter')")
        user_id = conn.execute("SELECT id FROM users").fetchone()[0]
        conn.execute("INSERT INTO audit_log (user_id, action, applicant_id, changes) "
                     "SELECT %s, 'update_follow_up', min(id), '{}' FROM applicants", (user_id,))
    run_reset()
    assert count("SELECT count(*) FROM applicants WHERE name = 'Hacked Name'") == 0
    assert count("SELECT count(*) FROM applicants WHERE follow_up_note = 'visitor wrote this'") == 0
    assert count("SELECT count(*) FROM audit_log") == 0


def test_removes_a_call_a_visitor_somehow_added(clean_tables, demo_mode):
    seeded()
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        conn.execute("INSERT INTO calls (vapi_call_id, raw_payload) VALUES ('visitor-1', '{\"demo\": true}')")
    run_reset()
    assert count("SELECT count(*) FROM calls WHERE vapi_call_id = 'visitor-1'") == 0


def test_the_logins_survive_the_reset(clean_tables, demo_mode):
    from app.auth import create_user
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        create_user(conn, "demo", LOGIN_PASSWORD, "recruiter")
    seeded()
    run_reset()
    assert count("SELECT count(*) FROM users WHERE username = 'demo'") == 1


def test_the_result_is_the_same_set_of_people_as_a_fresh_seed(clean_tables, demo_mode):
    seeded()
    with psycopg.connect(TEST_URL) as conn:
        before = conn.execute("SELECT name, phone_e164, temperature FROM applicants ORDER BY phone_e164").fetchall()
    run_reset()
    run_reset()  # running twice in a row is fine (a cron retry must not break anything)
    with psycopg.connect(TEST_URL) as conn:
        after = conn.execute("SELECT name, phone_e164, temperature FROM applicants ORDER BY phone_e164").fetchall()
    assert after == before


def test_a_failed_reseed_leaves_the_old_data_in_place(clean_tables, demo_mode, monkeypatch):
    """One transaction: delete + reseed succeed together or not at all, so the demo is never left empty."""
    from app import demo_reset, demo_seed
    seeded()
    names = count("SELECT count(*) FROM applicants")

    def boom(*_args, **_kwargs):
        raise RuntimeError("seed failed halfway")
    monkeypatch.setattr(demo_seed, "write_demo_rows", boom)
    with pytest.raises(RuntimeError):
        # autocommit: without reset()'s own transaction every DELETE would be saved on the spot
        with psycopg.connect(TEST_URL, autocommit=True) as conn:
            demo_reset.reset(conn)
    assert count("SELECT count(*) FROM applicants") == names
