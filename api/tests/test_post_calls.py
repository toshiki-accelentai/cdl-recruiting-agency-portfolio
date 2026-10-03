from datetime import timezone

import psycopg
import pytest

from app import main
from app.helpers import classify_temperature, normalize_phone
from app.schemas import IntakeRequest


def args(payload):
    return payload["message"]["toolCalls"][0]["function"]["arguments"]


def test_saves_applicant_and_call(client, payload, db):
    r = client.post("/calls", json=payload)
    assert r.status_code == 201
    assert r.json()["temperature"] == "MEDIUM"  # "within 7 days"

    row = db.execute(
        "SELECT name, phone_e164, city, state, zip_code, temperature FROM applicants"
    ).fetchone()
    assert row == ("John Smith", "+16727274656", "Tampa", "FL", "33605", "MEDIUM")

    vapi_id, applicant_id, raw = db.execute(
        "SELECT vapi_call_id, applicant_id, raw_payload FROM calls").fetchone()
    assert vapi_id == "01a0cfa8-a48b-7dda-9ccb-545929aaaf59"
    assert applicant_id == r.json()["applicant_id"]
    assert raw["message"]["toolCalls"][0]["id"] == "call_tJg2A9cg40h9OZokHRnbd5Nd"


def test_naive_callback_time_is_vancouver_local(client, payload, db):
    client.post("/calls", json=payload)
    (at,) = db.execute("SELECT preferred_callback_at FROM calls").fetchone()
    # 10:00 Vancouver on 2026-09-25 (PDT, UTC-7) is 17:00 UTC.
    assert at.astimezone(timezone.utc).hour == 17


def test_invalid_phone_rejected_and_nothing_saved(client, payload, db):
    args(payload)["phoneNumber"] = "12345"
    assert client.post("/calls", json=payload).status_code == 422
    assert db.execute("SELECT count(*) FROM applicants").fetchone()[0] == 0


def test_missing_name_rejected(client, payload, db):
    del args(payload)["name"]
    assert client.post("/calls", json=payload).status_code == 422
    assert db.execute("SELECT count(*) FROM applicants").fetchone()[0] == 0


def test_failed_call_insert_rolls_back_applicant(payload, db):
    """The point of A1: if the second insert fails, the first must not survive."""
    req = IntakeRequest.model_validate(payload)
    with psycopg.connect(main.database_url()) as conn:
        main.save_intake(conn, payload, req, "+16727274656")
    # Same vapi_call_id again: UNIQUE violation on calls, after the applicants insert ran.
    with pytest.raises(psycopg.errors.UniqueViolation):
        with psycopg.connect(main.database_url()) as conn:
            main.save_intake(conn, payload, req, "+16727274656")
    assert db.execute("SELECT count(*) FROM applicants").fetchone()[0] == 1
    assert db.execute("SELECT count(*) FROM calls").fetchone()[0] == 1


@pytest.mark.parametrize("raw,expected", [
    ("6727274656", "+16727274656"),
    ("(672) 727-4656", "+16727274656"),
    ("+1 672 727 4656", "+16727274656"),
    ("727-4656", None),
    ("", None),
])
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("immediately", "HOT"), ("within 3 days", "HOT"), ("within 7 days", "MEDIUM"),
    ("in two weeks", "WARM"), ("next month", "COLD"), ("", "COLD"),
])
def test_classify_temperature(raw, expected):
    assert classify_temperature(raw) == expected
