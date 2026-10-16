"""C1e: POST /call-reports stores VAPI's end-of-call report (summary, transcript, recording flag).

n8n forwards the report with the shared X-API-Key, same as POST /calls. Written before the code.
"""
import pytest
from fastapi.testclient import TestClient

from app.helpers import build_transcript
from tests.conftest import TEST_URL

CALL_ID = "01a0cfa8-a48b-7dda-9ccb-545929aaaf59"  # the id in the intake fixture
MESSAGES = [
    {"role": "system", "message": "You are an agent"},
    {"role": "bot", "message": "Thanks for calling Frontline CDL Staffing.", "secondsFromStart": 0.4},
    {"role": "user", "message": "Hi, I saw the posting.", "secondsFromStart": 6.25},
    {"role": "tool_calls", "toolCalls": []},
    {"role": "tool_call_result", "result": "ok"},
    {"role": "bot", "message": "   ", "secondsFromStart": 9.0},  # blank: dropped
    {"role": "bot", "message": "Great, can I get your name?", "secondsFromStart": 12.0},
]


def report(call_id=CALL_ID, **overrides):
    message = {
        "type": "end-of-call-report",
        "endedReason": "assistant-ended-call",
        "call": {"id": call_id, "customer": {"number": "+14155550123"}},
        "artifact": {"messages": MESSAGES, "transcript": "AI: hi\nUser: hello",
                     "recordingUrl": "https://example.invalid/private.wav"},
        "analysis": {"summary": "Driver wants regional work, six years experience."},
    }
    message.update(overrides)
    return {"message": message}


def call_row(db, vapi_id=CALL_ID):
    return db.execute(
        "SELECT summary, transcript, has_recording, report_received_at, caller_number, needs_review, "
        "review_reason, applicant_id FROM calls WHERE vapi_call_id = %s", (vapi_id,)).fetchone()


# --- the transcript builder, no database -----------------------------------------------------

def test_build_transcript_keeps_only_spoken_lines_with_speaker_and_start():
    assert build_transcript(MESSAGES, None) == [
        {"speaker": "agent", "text": "Thanks for calling Frontline CDL Staffing.", "start": 0.4},
        {"speaker": "driver", "text": "Hi, I saw the posting.", "start": 6.2},
        {"speaker": "agent", "text": "Great, can I get your name?", "start": 12.0},
    ]


def test_build_transcript_falls_back_to_the_plain_text():
    assert build_transcript(None, "AI: Hello there.\nUser: Hi.\nAI: Name?") == [
        {"speaker": "agent", "text": "Hello there.", "start": None},
        {"speaker": "driver", "text": "Hi.", "start": None},
        {"speaker": "agent", "text": "Name?", "start": None},
    ]


def test_build_transcript_is_limited_in_lines_and_line_length():
    many = [{"role": "user", "message": "x" * 5000, "secondsFromStart": i} for i in range(900)]
    lines = build_transcript(many, None)
    assert len(lines) == 500 and len(lines[0]["text"]) == 2000


# --- access ----------------------------------------------------------------------------------

def test_report_needs_the_api_key(clean_tables):
    from app.main import app
    assert TestClient(app).post("/call-reports", json=report()).status_code == 401


def test_other_message_types_are_ignored(client, db):
    r = client.post("/call-reports", json=report(type="status-update"))
    assert r.status_code == 200 and r.json() == {"ignored": True}
    assert db.execute("SELECT count(*) FROM calls").fetchone()[0] == 0


def test_report_without_a_call_id_is_rejected(client):
    body = report()
    del body["message"]["call"]["id"]
    assert client.post("/call-reports", json=body).status_code == 422


# --- a report for a call we already saved -----------------------------------------------------

def test_report_fills_summary_transcript_and_recording_flag(client, payload, db):
    client.post("/calls", json=payload)
    r = client.post("/call-reports", json=report())
    assert r.status_code == 200 and r.json()["created_placeholder"] is False
    summary, transcript, has_recording, received_at, caller, needs_review, reason, applicant_id = call_row(db)
    assert summary == "Driver wants regional work, six years experience."
    assert [line["speaker"] for line in transcript] == ["agent", "driver", "agent"]
    assert has_recording is True and received_at is not None
    assert caller == "+14155550123"
    assert needs_review is False and reason is None and applicant_id is not None  # intake data untouched


def test_report_never_stores_the_recording_link(client, payload, db):
    client.post("/calls", json=payload)
    client.post("/call-reports", json=report())
    stored = db.execute("SELECT summary::text || coalesce(transcript::text, '') || raw_payload::text FROM calls").fetchone()[0]
    assert "private.wav" not in stored


def test_legacy_summary_and_transcript_fields_are_accepted(client, payload, db):
    client.post("/calls", json=payload)
    body = report()
    body["message"]["analysis"] = {}
    body["message"]["summary"] = "Legacy summary."
    body["message"]["artifact"] = {"transcript": "AI: Hi\nUser: Hello"}
    client.post("/call-reports", json=body)
    summary, transcript, has_recording, *_ = call_row(db)
    assert summary == "Legacy summary." and len(transcript) == 2 and has_recording is False


def test_replayed_report_changes_nothing(client, payload, db):
    client.post("/calls", json=payload)
    client.post("/call-reports", json=report())
    client.post("/call-reports", json=report())
    assert db.execute("SELECT count(*) FROM calls").fetchone()[0] == 1


def test_blocked_caller_id_is_not_stored(client, payload, db):
    client.post("/calls", json=payload)
    body = report()
    body["message"]["call"]["customer"]["number"] = "anonymous"
    client.post("/call-reports", json=body)
    assert call_row(db)[4] is None


# --- a report for a call that never reached the intake step -----------------------------------

def test_report_without_an_intake_becomes_a_flagged_call_with_no_applicant(client, db):
    r = client.post("/call-reports", json=report(call_id="never-saved"))
    assert r.status_code == 201 and r.json()["created_placeholder"] is True
    summary, transcript, has_recording, _, caller, needs_review, reason, applicant_id = call_row(db, "never-saved")
    assert applicant_id is None and needs_review is True and reason == "no_intake"
    assert summary and transcript and has_recording is True and caller == "+14155550123"
    assert db.execute("SELECT count(*) FROM applicants").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM outbox").fetchone()[0] == 0  # nothing to sync to Zoho


def test_replayed_placeholder_report_is_one_call(client, db):
    client.post("/call-reports", json=report(call_id="never-saved"))
    second = client.post("/call-reports", json=report(call_id="never-saved"))
    assert second.status_code == 200
    assert db.execute("SELECT count(*) FROM calls").fetchone()[0] == 1


def test_intake_arriving_after_its_report_completes_the_call_instead_of_being_lost(client, payload, db):
    """If the report ever beats the tool call, the lead must still become an applicant."""
    client.post("/call-reports", json=report())
    r = client.post("/calls", json=payload)
    assert r.status_code == 201 and r.json()["duplicate"] is False and r.json()["applicant_id"] is not None
    summary, _, _, _, _, needs_review, reason, applicant_id = call_row(db)
    assert summary and applicant_id == r.json()["applicant_id"]
    assert needs_review is False and reason is None
    assert db.execute("SELECT count(*) FROM calls").fetchone()[0] == 1
    assert db.execute("SELECT count(*) FROM outbox").fetchone()[0] == 1  # the lead is queued for Zoho


def test_a_normal_replayed_intake_is_still_a_duplicate(client, payload):
    first = client.post("/calls", json=payload)
    second = client.post("/calls", json=payload)
    assert (first.status_code, second.status_code) == (201, 200) and second.json()["duplicate"] is True
