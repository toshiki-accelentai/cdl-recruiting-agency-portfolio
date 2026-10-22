"""Read side of the Applicant detail page: one person, their calls, and who changed what.

Login required (any role). Never returns raw_payload.
"""
from fastapi import APIRouter, Depends, HTTPException

from app.auth import current_user
from app.exposure import for_user
from app.dashboard import SELECT_CALLS, to_item
from app.db import db_connection

router = APIRouter(prefix="/api", dependencies=[Depends(current_user)])

HISTORY_LIMIT = 50

APPLICANT = """
SELECT a.id, a.name, a.phone_e164, a.callback_phone, a.city, a.state, a.zip_code, a.experience,
       a.readiness, a.temperature, a.zoho_candidate_id,
       a.follow_up_status, a.follow_up_note, a.follow_up_updated_at,
       (a.follow_up_updated_at IS NOT NULL AND EXISTS (
            SELECT 1 FROM calls newer
            WHERE newer.applicant_id = a.id AND newer.created_at > a.follow_up_updated_at)
       ) AS new_call_since
FROM applicants a WHERE a.id = %s
"""

TRANSCRIPTS = "SELECT id, transcript FROM calls WHERE applicant_id = %s"

HISTORY = f"""
SELECT h.id, h.action, u.username, h.call_id, h.changes, h.created_at
FROM audit_log h JOIN users u ON u.id = h.user_id
WHERE h.applicant_id = %s
ORDER BY h.created_at DESC, h.id DESC LIMIT {HISTORY_LIMIT}
"""


def to_applicant(row: tuple) -> dict:
    (applicant_id, name, phone, callback_phone, city, state, zip_code, experience, readiness,
     temperature, zoho_id, follow_up_status, follow_up_note, follow_up_updated_at, new_call_since) = row
    return {
        "id": applicant_id, "name": name, "phone": phone, "callback_phone": callback_phone,
        "city": city, "state": state, "zip_code": zip_code, "experience": experience,
        "readiness": readiness, "temperature": temperature, "zoho_candidate_id": zoho_id, "has_zoho_record": zoho_id is not None,
        "follow_up": {"status": follow_up_status, "note": follow_up_note,
                      "updated_at": follow_up_updated_at, "new_call_since": new_call_since},
    }


def to_history_item(row: tuple) -> dict:
    entry_id, action, username, call_id, changes, created_at = row
    return {"id": entry_id, "action": action, "username": username, "call_id": call_id,
            "changes": changes, "created_at": created_at}


def without_applicant(call: dict) -> dict:
    """The person is already at the top of the response; do not repeat them on every call."""
    return {key: value for key, value in call.items() if key != "applicant"}


@router.get("/applicants/{applicant_id}")
def get_applicant(applicant_id: int, user: dict = Depends(current_user)):
    with db_connection() as conn:
        row = conn.execute(APPLICANT, (applicant_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="applicant not found")
        calls = conn.execute(
            SELECT_CALLS + "WHERE c.applicant_id = %s ORDER BY c.created_at DESC, c.id DESC",
            (applicant_id,)).fetchall()
        transcripts = dict(conn.execute(TRANSCRIPTS, (applicant_id,)).fetchall())
        history = conn.execute(HISTORY, (applicant_id,)).fetchall()
    return for_user(user, {
        "applicant": to_applicant(row),
        "calls": [{**without_applicant(item), "transcript": transcripts.get(item["id"])}
                  for item in (to_item(r) for r in calls)],
        "history": [to_history_item(r) for r in history],
    })
