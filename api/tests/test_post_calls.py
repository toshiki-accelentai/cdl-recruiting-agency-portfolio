from datetime import timezone

import pytest

from app import main
from app.helpers import classify_temperature, normalize_phone


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


def test_invalid_phone_saves_call_flagged_for_review(client, payload, db):
    args(payload)["phoneNumber"] = "672 727"
    r = client.post("/calls", json=payload)
    assert r.status_code == 201
    assert r.json()["applicant_id"] is None and r.json()["needs_review"] is True
    assert db.execute("SELECT count(*) FROM applicants").fetchone()[0] == 0
    applicant_id, needs_review, reason, raw = db.execute(
        "SELECT applicant_id, needs_review, review_reason, raw_payload FROM calls").fetchone()
    assert applicant_id is None and needs_review is True and reason == "invalid_phone"
    assert raw["message"]["toolCalls"][0]["function"]["arguments"]["name"] == "John Smith"


def test_missing_name_saves_and_flags(client, payload, db):
    del args(payload)["name"]
    r = client.post("/calls", json=payload)
    assert r.status_code == 201 and r.json()["needs_review"] is True
    assert db.execute("SELECT review_reason FROM calls").fetchone()[0] == "missing_name"
    assert db.execute("SELECT name, phone_e164 FROM applicants").fetchone() == ("", "+16727274656")


def test_missing_name_on_repeat_call_keeps_existing_name(client, payload, db):
    client.post("/calls", json=payload)
    payload["message"]["call"]["id"] = "second-call"
    del args(payload)["name"]
    client.post("/calls", json=payload)
    assert db.execute("SELECT name FROM applicants").fetchone()[0] == "John Smith"


def test_clean_call_is_not_flagged(client, payload, db):
    r = client.post("/calls", json=payload)
    assert r.json()["needs_review"] is False
    assert db.execute("SELECT needs_review, review_reason FROM calls").fetchone() == (False, None)


def test_replayed_invalid_phone_call_is_idempotent(client, payload, db):
    args(payload)["phoneNumber"] = "672 727"
    first = client.post("/calls", json=payload)
    second = client.post("/calls", json=payload)
    assert (first.status_code, second.status_code) == (201, 200)
    assert second.json()["call_id"] == first.json()["call_id"]
    assert db.execute("SELECT count(*) FROM calls").fetchone()[0] == 1


def test_payload_without_call_id_still_rejected(client, payload):
    del payload["message"]["call"]["id"]
    assert client.post("/calls", json=payload).status_code == 422


def test_failed_call_insert_rolls_back_applicant(client, payload, db, monkeypatch):
    """The point of A1: if the call insert fails, the applicant insert must not survive."""
    def boom(_):
        raise RuntimeError("simulated failure while saving the call")

    monkeypatch.setattr(main, "Jsonb", boom)  # runs after the applicant insert, before the call insert
    with pytest.raises(RuntimeError):
        client.post("/calls", json=payload)
    assert db.execute("SELECT count(*) FROM applicants").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM calls").fetchone()[0] == 0


def test_replayed_call_is_idempotent(client, payload, db):
    first = client.post("/calls", json=payload)
    second = client.post("/calls", json=payload)
    assert first.status_code == 201 and first.json()["duplicate"] is False
    assert second.status_code == 200 and second.json()["duplicate"] is True
    assert second.json()["call_id"] == first.json()["call_id"]
    assert second.json()["applicant_id"] == first.json()["applicant_id"]
    assert db.execute("SELECT count(*) FROM applicants").fetchone()[0] == 1
    assert db.execute("SELECT count(*) FROM calls").fetchone()[0] == 1


def test_replay_does_not_modify_the_applicant(client, payload, db):
    client.post("/calls", json=payload)
    args(payload)["city"] = "Miami"  # same call id, different content
    client.post("/calls", json=payload)
    assert db.execute("SELECT city FROM applicants").fetchone()[0] == "Tampa"


def test_same_phone_new_call_reuses_applicant(client, payload, db):
    first = client.post("/calls", json=payload)
    payload["message"]["call"]["id"] = "second-call"
    payload["message"]["toolCalls"][0]["function"]["arguments"]["phoneNumber"] = "(672) 727-4656"
    second = client.post("/calls", json=payload)
    assert second.status_code == 201
    assert second.json()["applicant_id"] == first.json()["applicant_id"]
    assert db.execute("SELECT count(*) FROM applicants").fetchone()[0] == 1
    assert db.execute("SELECT count(*) FROM calls").fetchone()[0] == 2


def test_second_call_updates_only_the_fields_it_provides(client, payload, db):
    client.post("/calls", json=payload)
    payload["message"]["call"]["id"] = "second-call"
    a = args(payload)
    a["readiness"] = "immediately"
    a["zipCode"] = "33606"
    a["city"] = ""          # not provided this time: must NOT wipe "Tampa"
    a["experience"] = ""    # same
    r = client.post("/calls", json=payload)
    assert r.json()["temperature"] == "HOT"
    row = db.execute("SELECT city, zip_code, experience, readiness, temperature FROM applicants").fetchone()
    assert row == ("Tampa", "33606", "3 years 8 months", "immediately", "HOT")


def test_second_call_without_readiness_keeps_temperature(client, payload, db):
    client.post("/calls", json=payload)  # MEDIUM
    payload["message"]["call"]["id"] = "second-call"
    args(payload)["readiness"] = ""
    client.post("/calls", json=payload)
    assert db.execute("SELECT temperature FROM applicants").fetchone()[0] == "MEDIUM"


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


# ---- B1: outbox (DB row first, CRM sync after) ----

def test_clean_call_adds_one_pending_outbox_row(client, payload, db):
    r = client.post("/calls", json=payload)
    rows = db.execute(
        "SELECT call_id, applicant_id, status, attempts, last_error, sent_at FROM outbox").fetchall()
    assert rows == [(r.json()["call_id"], r.json()["applicant_id"], "pending", 0, None, None)]


def test_call_without_applicant_has_nothing_to_sync(client, payload, db):
    args(payload)["phoneNumber"] = "672 727"
    client.post("/calls", json=payload)
    assert db.execute("SELECT count(*) FROM outbox").fetchone()[0] == 0


def test_replay_does_not_add_a_second_outbox_row(client, payload, db):
    client.post("/calls", json=payload)
    client.post("/calls", json=payload)
    assert db.execute("SELECT count(*) FROM outbox").fetchone()[0] == 1


def test_repeat_caller_gets_one_outbox_row_per_call(client, payload, db):
    client.post("/calls", json=payload)
    payload["message"]["call"]["id"] = "second-call"
    client.post("/calls", json=payload)
    assert db.execute("SELECT count(*) FROM outbox").fetchone()[0] == 2


def test_failed_outbox_insert_rolls_back_call_and_applicant(client, payload, db, monkeypatch):
    """The outbox row is part of the same transaction: if it fails, nothing else survives."""
    monkeypatch.setattr(main, "INSERT_OUTBOX", "INSERT INTO no_such_table VALUES (%s, %s)")
    with pytest.raises(Exception):
        client.post("/calls", json=payload)
    for table in ("applicants", "calls", "outbox"):
        assert db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0, table
