"""Zoho client against a fake HTTP layer: no network, every failure injected on purpose."""
import json

import pytest

from app.helpers import parse_experience_years, split_name
from app.zoho import ZohoClient, ZohoError, candidate_fields


class FakeHttp:
    """Scripted responses; each item is (status, body) or an Exception to raise."""

    def __init__(self, *script):
        self.script = list(script)
        self.calls = []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append({"method": method, "url": url, "headers": headers,
                           "body": json.loads(body) if isinstance(body, bytes) and body[:1] in b"{[" else body})
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


TOKEN_OK = (200, {"access_token": "tok1", "expires_in": 3600})
TOKEN_OK_2 = (200, {"access_token": "tok2", "expires_in": 3600})


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def make(*script, clock=None):
    http = FakeHttp(*script)
    client = ZohoClient("cid", "secret", "refresh", http=http, clock=clock or Clock())
    return client, http


def token_calls(http):
    return [c for c in http.calls if "/oauth/v2/token" in c["url"]]


def test_token_is_cached_between_requests():
    client, http = make(TOKEN_OK, (204, None), (204, None))
    client.find_candidate_id("+12065550142")
    client.find_candidate_id("+12065550143")
    assert len(token_calls(http)) == 1


def test_token_is_refreshed_after_it_expires():
    clock = Clock()
    client, http = make(TOKEN_OK, (204, None), TOKEN_OK_2, (204, None), clock=clock)
    client.find_candidate_id("+12065550142")
    clock.now += 3600  # past expiry minus the safety margin
    client.find_candidate_id("+12065550142")
    assert len(token_calls(http)) == 2
    assert http.calls[-1]["headers"]["Authorization"] == "Zoho-oauthtoken tok2"


def test_401_refreshes_the_token_and_retries_once():
    client, http = make(TOKEN_OK, (401, {"code": "INVALID_TOKEN"}), TOKEN_OK_2, (204, None))
    assert client.find_candidate_id("+12065550142") is None
    assert len(token_calls(http)) == 2


def test_401_again_after_fresh_token_is_a_permanent_failure():
    client, _ = make(TOKEN_OK, (401, {}), TOKEN_OK_2, (401, {}))
    with pytest.raises(ZohoError) as err:
        client.find_candidate_id("+12065550142")
    assert err.value.kind == "fail"


@pytest.mark.parametrize("status", [500, 502, 503, 504, 429])
def test_server_trouble_and_rate_limits_are_retryable(status):
    client, _ = make(TOKEN_OK, (status, {"message": "nope"}))
    with pytest.raises(ZohoError) as err:
        client.find_candidate_id("+12065550142")
    assert err.value.kind == "retry"


@pytest.mark.parametrize("exc", [OSError("connection refused"), TimeoutError("timed out")])
def test_network_errors_are_retryable(exc):
    client, _ = make(TOKEN_OK, exc)
    with pytest.raises(ZohoError) as err:
        client.find_candidate_id("+12065550142")
    assert err.value.kind == "retry"


def test_bad_request_is_a_permanent_failure():
    client, _ = make(TOKEN_OK, (400, {"message": "invalid data"}))
    with pytest.raises(ZohoError) as err:
        client.find_candidate_id("+12065550142")
    assert err.value.kind == "fail" and "invalid data" in str(err.value)


def test_record_level_error_inside_a_200_is_a_permanent_failure():
    bad = (200, {"data": [{"code": "INVALID_DATA", "status": "error", "message": "bad zip"}]})
    client, _ = make(TOKEN_OK, bad)
    with pytest.raises(ZohoError) as err:
        client.add_note("c1", "t", "body")
    assert err.value.kind == "fail" and "bad zip" in str(err.value)


def test_invalid_client_when_minting_a_token_is_permanent_not_retried():
    client, _ = make((200, {"error": "invalid_client"}))
    with pytest.raises(ZohoError) as err:
        client.find_candidate_id("+12065550142")
    assert err.value.kind == "fail" and "invalid_client" in str(err.value)


def test_token_endpoint_outage_is_retryable():
    client, _ = make((503, {}))
    with pytest.raises(ZohoError) as err:
        client.find_candidate_id("+12065550142")
    assert err.value.kind == "retry"


def test_find_candidate_id_returns_none_on_204_and_id_on_match():
    client, _ = make(TOKEN_OK, (204, None))
    assert client.find_candidate_id("+12065550142") is None
    client, http = make(TOKEN_OK, (200, {"data": [{"id": "777"}]}))
    assert client.find_candidate_id("+12065550142") == "777"
    assert "phone=%2B12065550142" in http.calls[-1]["url"]


def test_upsert_creates_when_no_match():
    client, http = make(TOKEN_OK, (204, None),
                        (201, {"data": [{"code": "SUCCESS", "details": {"id": "555"}}]}))
    assert client.upsert_candidate("+12065550142", {"Last_Name": "Driver"}) == "555"
    assert http.calls[-1]["method"] == "POST" and http.calls[-1]["url"].endswith("/recruit/v2/Candidates")
    assert http.calls[-1]["body"]["data"] == [{"Last_Name": "Driver"}]


def test_upsert_updates_when_match_exists():
    client, http = make(TOKEN_OK, (200, {"data": [{"id": "777"}]}),
                        (200, {"data": [{"code": "SUCCESS", "details": {"id": "777"}}]}))
    assert client.upsert_candidate("+12065550142", {"Last_Name": "Driver"}) == "777"
    assert http.calls[-1]["method"] == "PUT" and http.calls[-1]["url"].endswith("/Candidates/777")


def test_add_note_matches_the_n8n_note_format():
    client, http = make(TOKEN_OK, (201, {"data": [{"code": "SUCCESS", "details": {"id": "n1"}}]}))
    client.add_note("777", "VAPI Intake - abc", "line1\nline2")
    assert http.calls[-1]["body"] == {"data": [{
        "Note_Title": "VAPI Intake - abc", "Note_Content": "line1\nline2",
        "Parent_Id": "777", "se_module": "Candidates"}]}


def test_candidate_fields_match_the_n8n_mapping():
    fields = candidate_fields({"name": "Mike Test Driver", "phone_e164": "+12065550199", "city": "Seattle",
                               "state": "WA", "zip_code": "98101", "experience": "2 years"})
    assert fields == {"Last_Name": "Driver", "First_Name": "Mike Test", "Phone": "+12065550199",
                      "City": "Seattle", "State": "WA", "Zip_Code": "98101",
                      "Experience_in_Years": 2, "Source": "Phone Call"}


@pytest.mark.parametrize("raw,first,last", [
    ("John Smith", "John", "Smith"), ("Cher", "", "Cher"), ("", "", "Unknown"), ("  A  B  C ", "A B", "C")])
def test_split_name(raw, first, last):
    assert split_name(raw) == (first, last)


@pytest.mark.parametrize("raw,years", [
    ("3 years 8 months", 3.67), ("2 years", 2), ("8 months", 0.67), ("1-2 years", 1.5),
    ("2+ years", 2), ("no experience", 0), ("", 0), ("under 6 months", 0.25), ("6-12 months", 0.75)])
def test_parse_experience_years(raw, years):
    assert parse_experience_years(raw) == years
