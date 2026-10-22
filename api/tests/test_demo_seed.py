"""C4 Part A step 2: the fictional data for the public demo server.

The seed must never run against the real database: it needs DEMO_MODE=1 AND an empty database.
Written before the code.
"""
import re

import psycopg
import pytest

from tests.conftest import TEST_URL
from tests.test_calls_api import web  # noqa: F401  (web is a pytest fixture)

FICTIONAL_PHONE = re.compile(r"^\+1\d{3}55501\d{2}$")  # 555-0100 to 555-0199 are reserved for fiction


def run_seed():
    from app import demo_seed
    with psycopg.connect(TEST_URL) as conn:
        demo_seed.seed(conn)


def count(sql):
    with psycopg.connect(TEST_URL) as conn:
        return conn.execute(sql).fetchone()[0]


@pytest.fixture
def demo_mode(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "1")


# --- the guards --------------------------------------------------------------------------------

def test_refuses_without_demo_mode(clean_tables, monkeypatch):
    from app.demo_seed import NotDemoMode
    monkeypatch.delenv("DEMO_MODE", raising=False)
    with pytest.raises(NotDemoMode):
        run_seed()
    assert count("SELECT count(*) FROM applicants") == 0


@pytest.mark.parametrize("value", ["", "0", "true", "yes"])
def test_only_the_exact_value_1_counts_as_demo_mode(clean_tables, monkeypatch, value):
    from app.demo_seed import NotDemoMode
    monkeypatch.setenv("DEMO_MODE", value)
    with pytest.raises(NotDemoMode):
        run_seed()


def test_refuses_a_database_that_already_has_data(clean_tables, demo_mode):
    """A second guard: pointed at the real database by mistake, it stops before writing anything."""
    from app.demo_seed import DatabaseNotEmpty
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        conn.execute("INSERT INTO applicants (name, phone_e164, temperature) VALUES ('Real', '+12065551234', 'HOT')")
    with pytest.raises(DatabaseNotEmpty):
        run_seed()
    assert count("SELECT count(*) FROM applicants") == 1


# --- the data ----------------------------------------------------------------------------------

def test_seeds_a_full_looking_roster_across_every_temperature(clean_tables, demo_mode):
    run_seed()
    assert 30 <= count("SELECT count(*) FROM applicants") <= 45
    assert count("SELECT count(DISTINCT temperature) FROM applicants") == 4
    assert count("SELECT min(n) FROM (SELECT count(*) n FROM applicants GROUP BY temperature) t") >= 3


def test_names_and_phones_are_all_different(clean_tables, demo_mode):
    run_seed()
    assert count("SELECT count(*) - count(DISTINCT name) FROM applicants") == 0
    assert count("SELECT count(*) - count(DISTINCT phone_e164) FROM applicants") == 0
    assert count("SELECT count(*) FROM applicants WHERE name ILIKE 'demo %'") == 0  # the seed stays free of 'Demo' labels


def test_the_roster_has_variety_in_when_and_how_people_called(clean_tables, demo_mode):
    run_seed()
    assert count("SELECT count(DISTINCT created_at::date) FROM calls") >= 8
    assert count("SELECT count(*) FROM applicants a WHERE (SELECT count(*) FROM calls c "
                 "WHERE c.applicant_id = a.id) >= 2") >= 3
    assert count("SELECT count(*) FROM calls WHERE preferred_callback_at < now()") >= 2  # overdue callbacks
    assert count("SELECT count(DISTINCT review_reason) FROM calls WHERE needs_review") >= 2
    assert count("SELECT count(*) FROM calls WHERE needs_review") >= 3
    assert count("SELECT count(DISTINCT state) FROM applicants") >= 15


def test_every_phone_number_is_fictional(clean_tables, demo_mode):
    run_seed()
    with psycopg.connect(TEST_URL) as conn:
        phones = [r[0] for r in conn.execute(
            "SELECT phone_e164 FROM applicants UNION ALL "
            "SELECT callback_phone FROM applicants WHERE callback_phone <> '' UNION ALL "
            "SELECT caller_number FROM calls WHERE caller_number IS NOT NULL")]
    assert phones and all(FICTIONAL_PHONE.fullmatch(p) for p in phones), phones


def test_shows_every_screen_state(clean_tables, demo_mode):
    run_seed()
    assert count("SELECT count(*) FROM outbox WHERE status = 'pending'") >= 1  # "waiting for Zoho"
    assert count("SELECT count(*) FROM outbox WHERE status = 'failed' AND last_error IS NOT NULL") >= 1
    assert count("SELECT count(*) FROM outbox WHERE status = 'sent'") >= 1
    assert count("SELECT count(*) FROM calls WHERE needs_review AND applicant_id IS NULL") >= 1
    assert count("SELECT count(DISTINCT follow_up_status) FROM applicants") >= 3
    assert count("SELECT count(*) FROM applicants a WHERE (SELECT count(*) FROM calls c "
                 "WHERE c.applicant_id = a.id) >= 2") >= 1  # someone who called twice


def test_every_call_has_a_summary_and_transcript(clean_tables, demo_mode):
    run_seed()
    assert count("SELECT count(*) FROM calls WHERE summary IS NULL OR transcript IS NULL") == 0


def test_exactly_the_two_sample_calls_have_a_recording(clean_tables, demo_mode):
    from app.recordings import DEMO_RECORDING_FILES
    run_seed()
    assert count("SELECT count(*) FROM calls WHERE has_recording") == 2
    with psycopg.connect(TEST_URL) as conn:
        ids = {r[0] for r in conn.execute("SELECT vapi_call_id FROM calls WHERE has_recording")}
    assert ids == set(DEMO_RECORDING_FILES)


def test_the_two_sample_calls_are_the_intake_and_the_flagged_hang_up(clean_tables, demo_mode):
    run_seed()
    with psycopg.connect(TEST_URL) as conn:
        intake = conn.execute("SELECT a.name, a.city, c.needs_review FROM calls c JOIN applicants a ON a.id = c.applicant_id "
                              "WHERE c.has_recording").fetchall()
        flagged = conn.execute("SELECT review_reason FROM calls WHERE has_recording AND applicant_id IS NULL").fetchall()
        lines = conn.execute("SELECT jsonb_array_length(transcript) FROM calls WHERE has_recording ORDER BY 1").fetchall()
    assert intake == [("Carlos Rivera", "Fresno", False)]
    assert flagged == [("no_intake",)]
    assert lines[0][0] >= 3 and lines[1][0] >= 20  # the real transcripts, with their real timestamps


def test_transcript_times_follow_the_audio_not_a_fixed_step(clean_tables, demo_mode):
    run_seed()
    with psycopg.connect(TEST_URL) as conn:
        starts = [t["start"] for t in conn.execute(
            "SELECT transcript FROM calls WHERE has_recording AND applicant_id IS NOT NULL").fetchone()[0]]
    assert starts == sorted(starts) and len(set(round(b - a, 1) for a, b in zip(starts, starts[1:]))) > 3


def test_no_zoho_ids_and_no_real_payloads(clean_tables, demo_mode):
    run_seed()
    assert count("SELECT count(*) FROM applicants WHERE zoho_candidate_id IS NOT NULL") == 0
    assert count("SELECT count(*) FROM calls WHERE NOT raw_payload ? 'demo'") == 0


def test_dates_are_relative_to_now(clean_tables, demo_mode):
    run_seed()
    assert count("SELECT count(*) FROM calls WHERE created_at > now() "
                 "OR created_at < now() - interval '14 days'") == 0
    assert count("SELECT count(*) FROM calls WHERE created_at > now() - interval '1 day'") >= 1  # calls today


def test_the_to_do_page_has_something_in_each_section(clean_tables, demo_mode, web):
    run_seed()
    todo = web.get("/api/todo").json()
    assert todo["attention"] and todo["call_back"]
    assert todo["summary"]["hot_waiting"] >= 1
