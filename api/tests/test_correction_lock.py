"""A repeat caller's new call must not undo what a recruiter corrected (owner decision 2026-10-26, "option 1").

The rule: a field a recruiter has changed through the dashboard is kept when the same phone number calls again. Fields the
recruiter never touched still follow the newest call. The callback time belongs to each call, so it is not affected.
Temperature follows readiness: a recruiter's change to either one keeps the temperature too. Written before the code.
"""
import pytest

from tests.test_calls_api import web  # noqa: F401  (web is a pytest fixture)


def args(payload):
    return payload["message"]["toolCalls"][0]["function"]["arguments"]


def first_call(client, payload):
    r = client.post("/calls", json=payload)
    assert r.status_code == 201
    return r.json()


def recruiter_fix(web, call_id, **body):
    r = web.patch(f"/api/calls/{call_id}", json=body)
    assert r.status_code == 200, r.text


def repeat_call(client, payload, call_id="second-call", **changes):
    payload["message"]["call"]["id"] = call_id
    args(payload).update(changes)
    r = client.post("/calls", json=payload)
    assert r.status_code == 201
    return r.json()


def applicant(db, *columns):
    return db.execute(f"SELECT {', '.join(columns)} FROM applicants").fetchone()


def test_a_corrected_field_survives_a_repeat_call(client, web, payload, db):
    call = first_call(client, payload)
    recruiter_fix(web, call["call_id"], city="Dallas")
    repeat_call(client, payload, city="Tampa Bay")
    assert applicant(db, "city") == ("Dallas",)


def test_fields_the_recruiter_did_not_touch_still_follow_the_newest_call(client, web, payload, db):
    call = first_call(client, payload)
    recruiter_fix(web, call["call_id"], city="Dallas")
    repeat_call(client, payload, city="Tampa Bay", zipCode="33606", experience="5 years")
    assert applicant(db, "city", "zip_code", "experience") == ("Dallas", "33606", "5 years")


def test_only_the_corrected_field_is_locked(client, web, payload, db):
    call = first_call(client, payload)
    recruiter_fix(web, call["call_id"], name="Jonathan Smith")
    repeat_call(client, payload, name="Johnny Smith", city="Orlando")
    assert applicant(db, "name", "city") == ("Jonathan Smith", "Orlando")


def test_a_corrected_state_and_zip_are_kept(client, web, payload, db):
    call = first_call(client, payload)
    recruiter_fix(web, call["call_id"], state="TX", zip_code="75001")
    repeat_call(client, payload, state="fl", zipCode="33606")
    assert applicant(db, "state", "zip_code") == ("TX", "75001")


def test_a_corrected_readiness_keeps_the_temperature_with_it(client, web, payload, db):
    call = first_call(client, payload)  # "within 7 days" = MEDIUM
    recruiter_fix(web, call["call_id"], readiness="within 3 days")  # the recruiter's change makes it HOT
    result = repeat_call(client, payload, readiness="within 14 days")
    assert applicant(db, "readiness", "temperature") == ("within 3 days", "HOT")
    assert result["temperature"] == "HOT"


def test_a_readiness_the_recruiter_wrote_in_their_own_words_keeps_the_temperature_it_was_given(client, web, payload, db):
    """Only readiness is in the change history here (an unknown phrase changes no temperature), so locking the
    temperature must follow the readiness lock by itself, or readiness and temperature would disagree."""
    call = first_call(client, payload)  # "within 7 days" = MEDIUM
    recruiter_fix(web, call["call_id"], readiness="maybe next spring, he said")
    assert applicant(db, "temperature") == ("MEDIUM",)
    result = repeat_call(client, payload, readiness="within 3 days")
    assert applicant(db, "readiness", "temperature") == ("maybe next spring, he said", "MEDIUM")
    assert result["temperature"] == "MEDIUM"


def test_a_corrected_temperature_is_kept_even_when_readiness_is_not(client, web, payload, db):
    call = first_call(client, payload)
    recruiter_fix(web, call["call_id"], temperature="COLD")
    result = repeat_call(client, payload, readiness="within 3 days")
    assert applicant(db, "readiness", "temperature") == ("within 3 days", "COLD")
    assert result["temperature"] == "COLD"


def test_an_applicant_nobody_corrected_still_follows_every_call(client, payload, db):
    first_call(client, payload)
    repeat_call(client, payload, city="Tampa Bay", readiness="within 3 days")
    assert applicant(db, "city", "temperature") == ("Tampa Bay", "HOT")


def test_a_correction_on_one_applicant_does_not_lock_another(client, web, payload, db):
    call = first_call(client, payload)
    recruiter_fix(web, call["call_id"], city="Dallas")
    payload["message"]["call"]["id"] = "other-caller"
    args(payload).update(phoneNumber="(206) 555-0177", city="Seattle", state="WA")
    client.post("/calls", json=payload)
    other = db.execute("SELECT city FROM applicants WHERE phone_e164 = '+12065550177'").fetchone()
    assert other == ("Seattle",)
    repeat_call(client, payload, call_id="other-again", city="Tacoma")
    assert db.execute("SELECT city FROM applicants WHERE phone_e164 = '+12065550177'").fetchone() == ("Tacoma",)
    assert db.execute("SELECT city FROM applicants WHERE phone_e164 = '+16727274656'").fetchone() == ("Dallas",)


def test_a_correction_that_changed_nothing_locks_nothing(client, web, payload, db):
    call = first_call(client, payload)
    recruiter_fix(web, call["call_id"], city="Tampa")  # same as stored: no audit row, no lock
    repeat_call(client, payload, city="Orlando")
    assert applicant(db, "city") == ("Orlando",)


def test_the_repeat_call_is_still_saved_and_each_call_keeps_its_own_callback_time(client, web, payload, db):
    call = first_call(client, payload)
    recruiter_fix(web, call["call_id"], city="Dallas")
    repeat_call(client, payload, preferredCallbackTime="2026-11-03T10:00:00")
    assert db.execute("SELECT count(*) FROM calls").fetchone()[0] == 2
    times = db.execute("SELECT preferred_callback_at IS NOT NULL FROM calls ORDER BY id").fetchall()
    assert times[1] == (True,)


def test_a_blank_answer_never_wipes_a_corrected_field(client, web, payload, db):
    call = first_call(client, payload)
    recruiter_fix(web, call["call_id"], city="Dallas")
    repeat_call(client, payload, city="")
    assert applicant(db, "city") == ("Dallas",)


def test_a_replayed_call_still_changes_nothing(client, web, payload, db):
    call = first_call(client, payload)
    recruiter_fix(web, call["call_id"], city="Dallas")
    replay = client.post("/calls", json=payload)  # same call id again
    assert replay.json()["duplicate"] is True
    assert applicant(db, "city") == ("Dallas",)
