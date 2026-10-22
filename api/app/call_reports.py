"""End-of-call reports from VAPI (via n8n) and the recording playback link.

POST /call-reports   n8n only (X-API-Key). Stores the summary, the transcript lines and a "has recording"
                     flag on the call. A report for a call that never reached the intake step becomes a
                     flagged call with no applicant, so a stranger's call is never silently dropped.
GET  /api/calls/{id}/recording   logged-in recruiters. Redirects to a fresh 30-minute signed link.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse, RedirectResponse
from psycopg.types.json import Jsonb

from app import recordings
from app.api_key import require_api_key, require_internal_caller
from app.auth import current_user
from app.db import db_connection
from app.helpers import build_transcript, normalize_phone
from app.schemas import BaseModel, Customer
from app.logs import short

logger = logging.getLogger(__name__)

router = APIRouter()

REPORT_TYPE = "end-of-call-report"
MAX_SUMMARY_LENGTH = 4000
NO_STORE = {"Cache-Control": "no-store"}  # a signed link must never be cached or shared

UPDATE_REPORT = """
UPDATE calls SET summary = COALESCE(%(summary)s, summary),
                 transcript = COALESCE(%(transcript)s, transcript),
                 has_recording = has_recording OR %(has_recording)s,
                 report_received_at = now(),
                 caller_number = COALESCE(%(caller)s, caller_number)
WHERE vapi_call_id = %(vapi_call_id)s RETURNING id
"""

# The call never reached the intake step (a non-driver, a hang-up): keep it, flagged, with no applicant.
INSERT_PLACEHOLDER = """
INSERT INTO calls (vapi_call_id, applicant_id, raw_payload, needs_review, review_reason,
                   summary, transcript, has_recording, report_received_at, caller_number)
VALUES (%(vapi_call_id)s, NULL, %(stub)s, true, 'no_intake',
        %(summary)s, %(transcript)s, %(has_recording)s, now(), %(caller)s)
ON CONFLICT (vapi_call_id) DO UPDATE SET
    summary = COALESCE(EXCLUDED.summary, calls.summary),
    transcript = COALESCE(EXCLUDED.transcript, calls.transcript),
    has_recording = calls.has_recording OR EXCLUDED.has_recording,
    report_received_at = now(),
    caller_number = COALESCE(EXCLUDED.caller_number, calls.caller_number)
RETURNING id, (xmax = 0) AS inserted
"""


class ReportCall(BaseModel):
    id: str
    customer: Customer | None = None


class ReportMessage(BaseModel):
    type: str
    call: ReportCall
    endedReason: str | None = None
    artifact: dict | None = None
    analysis: dict | None = None
    # older report shape: these sat directly on the message
    summary: str | None = None
    transcript: str | None = None
    messages: list | None = None
    recordingUrl: str | None = None


class ReportRequest(BaseModel):
    message: ReportMessage


def _summary(message: ReportMessage) -> str | None:
    analysis = message.analysis or {}
    text = analysis.get("summary") if isinstance(analysis.get("summary"), str) else message.summary
    text = (text or "").strip()
    return text[:MAX_SUMMARY_LENGTH] or None


@router.post("/call-reports", dependencies=[Depends(require_internal_caller), Depends(require_api_key)])
def post_call_report(req: ReportRequest, response: Response):
    message = req.message
    if message.type != REPORT_TYPE:
        return {"ignored": True}

    artifact = message.artifact or {}
    lines = build_transcript(artifact.get("messages") or message.messages,
                             artifact.get("transcript") or message.transcript)
    values = {
        "vapi_call_id": message.call.id,
        "summary": _summary(message),
        "transcript": Jsonb(lines) if lines else None,
        "has_recording": bool(artifact.get("recordingUrl") or message.recordingUrl),
        "caller": normalize_phone(message.call.customer.number or "") if message.call.customer else None,
        "stub": Jsonb({"source": REPORT_TYPE, "endedReason": message.endedReason}),  # the report itself is not kept
    }
    try:
        with db_connection() as conn:
            with conn.transaction():
                row = conn.execute(UPDATE_REPORT, values).fetchone()
                if row is not None:
                    return {"call_id": row[0], "created_placeholder": False}
                call_id, inserted = conn.execute(INSERT_PLACEHOLDER, values).fetchone()
    except Exception as exc:  # re-raised: the 500 tells n8n "not saved". No caller data in the log.
        logger.error("report save failed %s: %s", type(exc).__name__, short(exc))
        raise
    if inserted:
        response.status_code = 201
        logger.info("report saved as flagged call call_id=%s", call_id)
    return {"call_id": call_id, "created_placeholder": bool(inserted)}


@router.get("/api/calls/{call_id}/recording")
def get_recording(call_id: int, _user: dict = Depends(current_user)):
    with db_connection() as conn:
        row = conn.execute("SELECT vapi_call_id, has_recording FROM calls WHERE id = %s", (call_id,)).fetchone()
    if row is None or not row[1]:
        raise HTTPException(status_code=404, detail="no recording for this call")
    demo_folder = recordings.demo_recordings_dir()
    if demo_folder is not None:  # the demo server: a local sample file, never VAPI
        path = recordings.demo_recording_file(demo_folder, row[0])
        if path is None:
            raise HTTPException(status_code=404, detail="no recording for this call")
        return FileResponse(path, media_type="audio/wav", headers=NO_STORE)
    try:
        url = recordings.signed_recording_url(row[0])
    except ValueError:
        raise HTTPException(status_code=404, detail="no recording for this call")
    except recordings.NotConfigured:
        raise HTTPException(status_code=503, detail="recordings are not configured")
    except recordings.VapiError as exc:
        logger.error("recording lookup failed call_id=%s: %s", call_id, short(exc))
        raise HTTPException(status_code=502, detail="could not reach the recording service")
    if url is None:
        raise HTTPException(status_code=404, detail="no recording for this call")
    return RedirectResponse(url, status_code=302, headers=NO_STORE)
