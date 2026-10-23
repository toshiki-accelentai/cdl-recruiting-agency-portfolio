"""C1c step 2a: PATCH /api/calls/{id} corrects the applicant behind a call. Written before the code."""
import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.conftest import TEST_API_KEY, TEST_URL
from tests.test_calls_api import add_call, web  # noqa: F401  (web is a pytest fixture)


def q(sql, params=()):
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        return conn.execute(sql, params).fetchall()


def patch(web, call_id, **body):
    return web.patch(f"/api/calls/{call_id}", json=body)


def audit_rows():
    return q("SELECT action, call_id, applicant_id, changes FROM audit_log ORDER BY id")


def outbox_rows():
    return q("SELECT kind, status, call_id, applicant_id FROM outbox ORDER BY id")


# --- access and validation ------------------------------------------------------------------

def test_patch_needs_a_login_and_the_n8n_key_is_not_enough(clean_tables):
    from app.main import app
    call_id = add_call()
    assert TestClient(app).patch(f"/api/calls/{call_id}", json={"name": "X"}).status_code == 401
    keyed = TestClient(app, headers={"X-API-Key": TEST_API_KEY})
    assert keyed.patch(f"/api/calls/{call_id}", json={"name": "X"}).status_code == 401


def test_unknown_call_is_404(web):
    assert patch(web, 999999, name="X").status_code == 404


@pytest.mark.parametrize("body", [
    {},                                  # nothing to change
    {"temperature": "BOILING"},          # not one of HOT / MEDIUM / WARM / COLD
    {"name": "Valid Name", "temperature": "BOILING"},
    {"name": "Valid Name", "id": 7},     # a valid field must not smuggle a forbidden one in
    {"name": "Valid Name", "zoho_candidate_id": "999"},
    {"id": 7},
    {"name": "   "},                     # blank
    {"name": "x" * 101},
    {"state": "Florida"},                # must be a 2-letter code
    {"zip_code": "1" * 11},
    {"phone": "12345"},                  # not a usable US number
])
def test_bad_input_is_rejected_and_changes_nothing(web, body):
    call_id = add_call("Jane Roe", "+12065550199")
    assert web.patch(f"/api/calls/{call_id}", json=body).status_code == 422
    assert audit_rows() == [] and outbox_rows() == []
    assert q("SELECT name FROM applicants") == [("Jane Roe",)]


# --- correcting an existing applicant -------------------------------------------------------

def test_correcting_a_name_updates_it_audits_it_and_queues_a_zoho_update(web):
    call_id = add_call("Jane Roe", "+12065550199")
    resp = patch(web, call_id, name="Jane Q. Roe")
    assert resp.status_code == 200
    assert resp.json()["applicant"]["name"] == "Jane Q. Roe"
    assert q("SELECT name FROM applicants") == [("Jane Q. Roe",)]
    (action, audited_call, applicant_id, changes), = audit_rows()
    assert (action, audited_call) == ("correct_applicant", call_id)
    assert changes == {"name": {"from": "Jane Roe", "to": "Jane Q. Roe"}}
    assert q("SELECT username FROM users WHERE id = (SELECT user_id FROM audit_log)") == [("demo",)]
    assert outbox_rows() == [("correction", "pending", None, applicant_id)]


def test_phone_is_normalized_and_the_audit_records_old_and_new(web):
    call_id = add_call("Jane Roe", "+12065550199")
    assert patch(web, call_id, phone="(206) 555-0123").status_code == 200
    assert q("SELECT phone_e164 FROM applicants") == [("+12065550123",)]
    assert audit_rows()[0][3] == {"phone": {"from": "+12065550199", "to": "+12065550123"}}


def test_state_is_uppercased(web):
    call_id = add_call()
    assert patch(web, call_id, state="nv").json()["applicant"]["state"] == "NV"


def test_correcting_readiness_recomputes_the_temperature(web):
    call_id = add_call(temperature="COLD")
    resp = patch(web, call_id, readiness="within 3 days")
    assert resp.json()["applicant"]["temperature"] == "HOT"
    assert q("SELECT temperature FROM applicants") == [("HOT",)]


def test_a_recruiter_can_set_the_temperature_after_talking_to_the_applicant(web):
    call_id = add_call(temperature="COLD")
    resp = patch(web, call_id, temperature="HOT")
    assert resp.status_code == 200 and resp.json()["applicant"]["temperature"] == "HOT"
    assert q("SELECT temperature FROM applicants") == [("HOT",)]
    assert audit_rows()[0][3] == {"temperature": {"from": "COLD", "to": "HOT"}}
    assert [r[0] for r in outbox_rows()] == ["correction"]


def test_an_explicit_temperature_wins_over_the_one_computed_from_readiness(web):
    call_id = add_call(temperature="COLD")
    resp = patch(web, call_id, readiness="within 3 days", temperature="WARM")
    assert resp.json()["applicant"]["temperature"] == "WARM"   # 'within 3 days' alone would give HOT


def test_readiness_the_code_does_not_know_leaves_the_temperature_alone(web):
    call_id = add_call(temperature="HOT")
    resp = patch(web, call_id, readiness="tomorrow")
    applicant = resp.json()["applicant"]
    assert applicant["readiness"] == "tomorrow" and applicant["temperature"] == "HOT"
    assert q("SELECT readiness, temperature FROM applicants") == [("tomorrow", "HOT")]
    assert audit_rows()[0][3] == {"readiness": {"from": "next week", "to": "tomorrow"}}


def test_saving_the_same_values_changes_nothing_and_writes_no_audit_or_outbox(web):
    call_id = add_call("Jane Roe", "+12065550199")
    assert patch(web, call_id, name="Jane Roe", city="Tampa").status_code == 200
    assert audit_rows() == [] and outbox_rows() == []


def test_a_phone_that_belongs_to_another_applicant_is_rejected_and_names_the_owner(web):
    other_call = add_call("Other Driver", "+12065550111")
    call_id = add_call("Jane Roe", "+12065550199")
    resp = patch(web, call_id, phone="206-555-0111", name="Should Not Be Saved")
    assert resp.status_code == 409
    detail = resp.json()["detail"]
    assert detail["existing_applicant"]["name"] == "Other Driver"
    assert isinstance(detail["existing_applicant"]["id"], int)
    # all or nothing: the name in the same request was not saved either
    assert q("SELECT name, phone_e164 FROM applicants ORDER BY id") == [
        ("Other Driver", "+12065550111"), ("Jane Roe", "+12065550199")]
    assert audit_rows() == [] and outbox_rows() == []
    assert other_call != call_id


def test_fixing_a_missing_name_clears_the_review_flag(web):
    call_id = add_call("", "+12065550199", needs_review=True, review_reason="missing_name")
    resp = patch(web, call_id, name="Jane Roe")
    assert resp.json()["needs_review"] is False and resp.json()["review_reason"] is None
    assert q("SELECT needs_review, review_reason FROM calls") == [(False, None)]


def test_the_outbox_correction_row_points_at_its_audit_row(web):
    call_id = add_call("Jane Roe", "+12065550199")
    patch(web, call_id, name="Jane Q. Roe")
    assert q("SELECT o.audit_id = a.id FROM outbox o, audit_log a") == [(True,)]


def run(sql, params=()):
    with psycopg.connect(TEST_URL, autocommit=True) as conn:
        conn.execute(sql, params)


def test_the_database_refuses_a_correction_row_without_an_audit_row(web):
    add_call("Jane Roe", "+12065550199")
    (applicant_id,) = q("SELECT id FROM applicants")[0]
    with pytest.raises(psycopg.errors.CheckViolation):
        run("INSERT INTO outbox (kind, applicant_id) VALUES ('correction', %s)", (applicant_id,))


def test_the_database_refuses_an_intake_row_that_carries_an_audit_row(web):
    call_id = add_call("Jane Roe", "+12065550199")
    (applicant_id,) = q("SELECT id FROM applicants")[0]
    (user_id,) = q("SELECT id FROM users")[0]
    run("INSERT INTO audit_log (user_id, action, applicant_id, changes) "
        "VALUES (%s, 'correct_applicant', %s, '{}'::jsonb)", (user_id, applicant_id))
    with pytest.raises(psycopg.errors.CheckViolation):
        run("INSERT INTO outbox (kind, applicant_id, call_id, audit_id) "
            "VALUES ('intake', %s, %s, (SELECT id FROM audit_log))", (applicant_id, call_id))


# --- calls with no applicant (invalid phone) ------------------------------------------------

def test_giving_a_valid_phone_to_a_call_with_no_applicant_creates_and_attaches_one(web):
    call_id = add_call(phone=None, needs_review=True, review_reason="invalid_phone")
    resp = patch(web, call_id, phone="206-555-0177", name="New Driver", city="Reno", state="nv")
    assert resp.status_code == 200
    body = resp.json()
    assert body["attached_to_existing"] is False
    assert body["applicant"]["name"] == "New Driver" and body["applicant"]["state"] == "NV"
    assert body["needs_review"] is False and body["review_reason"] is None
    (applicant_id,) = q("SELECT id FROM applicants")[0]
    assert q("SELECT applicant_id FROM calls") == [(applicant_id,)]
    # the call never reached Zoho, so it needs its normal intake row, tied to the call
    assert outbox_rows() == [("intake", "pending", call_id, applicant_id)]
    (action, _, _, changes), = audit_rows()
    assert action == "attach_applicant" and changes["created_new_applicant"] is True


def test_phone_only_attaches_but_the_call_stays_flagged_until_a_name_is_given(web):
    call_id = add_call(phone=None, needs_review=True, review_reason="invalid_phone")
    resp = patch(web, call_id, phone="206-555-0177")
    assert resp.status_code == 200
    assert resp.json()["needs_review"] is True and resp.json()["review_reason"] == "missing_name"


def test_a_new_applicant_can_be_given_a_temperature_straight_away(web):
    call_id = add_call(phone=None, needs_review=True, review_reason="invalid_phone")
    resp = patch(web, call_id, phone="206-555-0177", name="New Driver", temperature="MEDIUM")
    assert resp.json()["applicant"]["temperature"] == "MEDIUM"


def test_a_call_with_no_applicant_cannot_be_patched_without_a_phone(web):
    call_id = add_call(phone=None, needs_review=True, review_reason="invalid_phone")
    assert patch(web, call_id, name="Nobody").status_code == 422
    assert q("SELECT count(*) FROM applicants") == [(0,)]


def test_a_phone_that_already_has_an_applicant_attaches_without_overwriting_it(web):
    add_call("Existing Driver", "+12065550142")
    call_id = add_call(phone=None, needs_review=True, review_reason="invalid_phone")
    resp = patch(web, call_id, phone="(206) 555-0142", name="Different Name")
    assert resp.status_code == 200
    assert resp.json()["attached_to_existing"] is True
    assert resp.json()["applicant"]["name"] == "Existing Driver"   # not overwritten
    assert q("SELECT count(*) FROM applicants") == [(1,)]
    assert resp.json()["needs_review"] is False
    assert [r[0] for r in outbox_rows()] == ["intake"]
    assert audit_rows()[0][3]["created_new_applicant"] is False
