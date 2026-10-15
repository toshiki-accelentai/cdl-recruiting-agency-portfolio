"""C1f: the caller ID (call.customer.number) is the applicant's identity; the spoken number is the callback number.

Fallback chain: valid caller ID -> valid spoken number -> flag the call for review.
"""
import pytest

from app.helpers import pick_phones

CALLER_ID = "+14155550123"
SPOKEN_FROM_FIXTURE = "+16727274656"  # the fixture's phoneNumber "6727274656"


def args(payload):
    return payload["message"]["toolCalls"][0]["function"]["arguments"]


def set_caller_id(payload, number):
    payload["message"]["call"]["customer"] = {"number": number}


def applicant_row(db):
    return db.execute("SELECT phone_e164, callback_phone FROM applicants").fetchall()


# --- the chain itself, no database --------------------------------------------------------

@pytest.mark.parametrize("caller_id, spoken, expected", [
    (CALLER_ID, "6727274656", (CALLER_ID, SPOKEN_FROM_FIXTURE)),  # differ: both kept
    (CALLER_ID, "(415) 555-0123", (CALLER_ID, "")),               # same number: no callback
    (CALLER_ID, "672 727", (CALLER_ID, "")),                      # garbage spoken: not stored
    (None, "6727274656", (SPOKEN_FROM_FIXTURE, "")),              # web call: spoken is identity
    ("anonymous", "6727274656", (SPOKEN_FROM_FIXTURE, "")),       # blocked ID
    ("", "6727274656", (SPOKEN_FROM_FIXTURE, "")),
    (None, "672 727", (None, "")),                                # nothing usable
    ("anonymous", "", (None, "")),
])
def test_pick_phones(caller_id, spoken, expected):
    assert pick_phones(caller_id, spoken) == expected


# --- through POST /calls ------------------------------------------------------------------

def test_caller_id_becomes_identity_and_spoken_becomes_callback(client, payload, db):
    set_caller_id(payload, CALLER_ID)
    r = client.post("/calls", json=payload)
    assert r.status_code == 201 and r.json()["needs_review"] is False
    assert applicant_row(db) == [(CALLER_ID, SPOKEN_FROM_FIXTURE)]


def test_same_caller_id_with_misheard_spoken_digits_is_one_applicant(client, payload, db):
    set_caller_id(payload, CALLER_ID)
    client.post("/calls", json=payload)
    payload["message"]["call"]["id"] = "second-call"
    args(payload)["phoneNumber"] = "6727274657"  # one digit transcribed differently
    r = client.post("/calls", json=payload)
    assert r.status_code == 201
    assert applicant_row(db) == [(CALLER_ID, "+16727274657")]  # latest callback wins
    assert db.execute("SELECT count(*) FROM calls").fetchone()[0] == 2


def test_invalid_spoken_number_does_not_wipe_stored_callback(client, payload, db):
    set_caller_id(payload, CALLER_ID)
    client.post("/calls", json=payload)
    payload["message"]["call"]["id"] = "second-call"
    args(payload)["phoneNumber"] = "672 727"
    client.post("/calls", json=payload)
    assert applicant_row(db) == [(CALLER_ID, SPOKEN_FROM_FIXTURE)]


def test_caller_id_rescues_an_invalid_spoken_number(client, payload, db):
    set_caller_id(payload, CALLER_ID)
    args(payload)["phoneNumber"] = "672 727"
    r = client.post("/calls", json=payload)
    assert r.status_code == 201 and r.json()["needs_review"] is False
    assert r.json()["applicant_id"] is not None
    assert applicant_row(db) == [(CALLER_ID, "")]
    assert db.execute("SELECT review_reason FROM calls").fetchone()[0] is None


def test_web_call_without_caller_id_uses_the_spoken_number(client, payload, db):
    payload["message"]["call"]["customer"] = {}  # web calls carry no number
    r = client.post("/calls", json=payload)
    assert r.status_code == 201 and r.json()["needs_review"] is False
    assert applicant_row(db) == [(SPOKEN_FROM_FIXTURE, "")]


def test_blocked_caller_id_with_invalid_spoken_is_flagged_not_lost(client, payload, db):
    set_caller_id(payload, "anonymous")
    args(payload)["phoneNumber"] = "672 727"
    r = client.post("/calls", json=payload)
    assert r.status_code == 201
    assert r.json()["applicant_id"] is None and r.json()["needs_review"] is True
    assert db.execute("SELECT review_reason FROM calls").fetchone()[0] == "invalid_phone"
    assert db.execute("SELECT count(*) FROM applicants").fetchone()[0] == 0


def test_customer_null_in_payload_is_accepted(client, payload, db):
    payload["message"]["call"]["customer"] = None
    assert client.post("/calls", json=payload).status_code == 201
