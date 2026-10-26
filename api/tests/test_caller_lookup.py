"""GET /applicants/lookup: n8n asks "have we talked to this caller before?" before it asks Zoho.

Owner decision 2026-10-23: an existing caller is anyone in our database, even before the worker has
copied them to Zoho, and they are greeted by name. Written before the code.
"""
from fastapi.testclient import TestClient

from tests.conftest import TEST_API_KEY


ON_FILE = {"city": "Dallas", "state": "TX", "zipCode": "75201", "experience": "5 years", "readiness": "within 7 days"}
BLANK = {key: "" for key in ON_FILE}


def add_applicant(db, name="Maria De La Cruz", phone="+12065550101", **details):
    d = {**BLANK, **details}
    db.execute("INSERT INTO applicants (name, phone_e164, city, state, zip_code, experience, readiness, temperature) "
               "VALUES (%s, %s, %s, %s, %s, %s, %s, 'HOT')",
               (name, phone, d["city"], d["state"], d["zipCode"], d["experience"], d["readiness"]))


def lookup(client, phone):
    return client.get("/applicants/lookup", params={"phone": phone})


def test_a_known_caller_is_found_with_their_name(client, db):
    add_applicant(db)
    r = lookup(client, "+12065550101")
    assert r.status_code == 200
    assert r.json()["found"] is True and r.json()["name"] == "Maria De La Cruz"


def test_a_known_caller_comes_with_the_details_on_file_so_the_agent_can_send_them_to_the_save_tool(client, db):
    add_applicant(db, **ON_FILE)
    assert lookup(client, "+12065550101").json() == {"found": True, "name": "Maria De La Cruz", **ON_FILE}


def test_details_the_caller_never_gave_come_back_blank_not_missing(client, db):
    add_applicant(db, city="Dallas")
    body = lookup(client, "+12065550101").json()
    assert body["city"] == "Dallas" and body["zipCode"] == "" and body["readiness"] == ""


def test_the_number_is_normalised_before_the_search(client, db):
    add_applicant(db)
    assert lookup(client, "(206) 555-0101").json()["found"] is True


def test_a_caller_who_is_only_in_the_database_not_yet_in_zoho_is_still_found(client, db):
    add_applicant(db)  # no zoho_candidate_id: the worker has not synced them yet
    assert lookup(client, "+12065550101").json()["found"] is True


def test_an_unknown_caller_is_not_found_and_gets_no_name_or_details(client, db):
    add_applicant(db, **ON_FILE)
    assert lookup(client, "+12065559999").json() == {"found": False, "name": "", **BLANK}


def test_the_answer_carries_only_what_the_save_tool_needs(client, db):
    """Not the phone, ids, notes, temperature or history: this goes into the call's prompt and VAPI's logs."""
    add_applicant(db, **ON_FILE)
    assert set(lookup(client, "+12065550101").json()) == {"found", "name", *ON_FILE}


def test_a_number_that_is_not_a_us_number_is_rejected(client, db):
    assert lookup(client, "+442071234567").status_code == 422
    assert lookup(client, "").status_code == 422


def test_the_lookup_needs_the_api_key(clean_tables):
    from app.main import app
    assert TestClient(app).get("/applicants/lookup", params={"phone": "+12065550101"}).status_code == 401
    wrong = TestClient(app, headers={"X-API-Key": TEST_API_KEY + "x"})
    assert wrong.get("/applicants/lookup", params={"phone": "+12065550101"}).status_code == 401


def test_the_lookup_is_hidden_from_the_public_proxy(client, db):
    add_applicant(db)
    r = client.get("/applicants/lookup", params={"phone": "+12065550101"},
                   headers={"X-Forwarded-For": "203.0.113.5"})
    assert r.status_code == 404
