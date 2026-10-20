"""Data behind the recruiter To do page.

attention: one row per CALL that is broken (flagged needs_review, or its Zoho save failed).
call_back: one row per PERSON who should be phoned (follow-up 'to_call', or a call arrived after
           the last follow-up). A person with five calls is still one row.
Login required (any role). Never returns raw_payload.
"""
from fastapi import APIRouter, Depends

from app.auth import current_user
from app.dashboard import SELECT_CALLS, to_item
from app.db import db_connection
from app.schemas import BUSINESS_TZ

router = APIRouter(prefix="/api", dependencies=[Depends(current_user)])

ATTENTION = SELECT_CALLS + "WHERE c.needs_review OR o.status = 'failed' ORDER BY c.created_at DESC, c.id DESC"

# One row per applicant: join the latest call and the call count. The new-call marker is the same
# rule as the calls list: a call newer than the last follow-up change.
CALL_BACK = """
SELECT a.id, a.name, a.phone_e164, a.callback_phone, a.city, a.state, a.zip_code, a.experience,
       a.readiness, a.temperature, a.zoho_candidate_id,
       a.follow_up_status, a.follow_up_note, a.follow_up_updated_at,
       lc.created_at, lc.preferred_callback_at, cnt.n,
       (a.follow_up_updated_at IS NOT NULL AND lc.created_at > a.follow_up_updated_at) AS new_call_since
FROM applicants a
JOIN LATERAL (SELECT created_at, preferred_callback_at FROM calls
              WHERE applicant_id = a.id ORDER BY created_at DESC, id DESC LIMIT 1) lc ON true
JOIN LATERAL (SELECT count(*) AS n FROM calls WHERE applicant_id = a.id) cnt ON true
WHERE a.follow_up_status = 'to_call'
   OR (a.follow_up_updated_at IS NOT NULL AND lc.created_at > a.follow_up_updated_at)
ORDER BY CASE a.temperature WHEN 'HOT' THEN 0 WHEN 'MEDIUM' THEN 1 WHEN 'WARM' THEN 2 ELSE 3 END,
         lc.preferred_callback_at ASC NULLS LAST, lc.created_at DESC, a.id
"""

CALLS_TODAY = "SELECT count(*) FROM calls WHERE created_at >= date_trunc('day', now() AT TIME ZONE %s) AT TIME ZONE %s"
SYNC_PROBLEMS = "SELECT count(*) FROM outbox WHERE status = 'failed'"


def to_call_back_item(row: tuple) -> dict:
    (applicant_id, name, phone, callback_phone, city, state, zip_code, experience, readiness,
     temperature, zoho_id, follow_up_status, follow_up_note, follow_up_updated_at,
     latest_call_at, callback_at, call_count, new_call_since) = row
    return {
        "applicant": {
            "id": applicant_id, "name": name, "phone": phone, "callback_phone": callback_phone,
            "city": city, "state": state, "zip_code": zip_code, "experience": experience,
            "readiness": readiness, "temperature": temperature, "zoho_candidate_id": zoho_id,
            "follow_up": {"status": follow_up_status, "note": follow_up_note,
                          "updated_at": follow_up_updated_at, "new_call_since": new_call_since},
        },
        "call_count": call_count,
        "latest_call_at": latest_call_at,
        "preferred_callback_at": callback_at,
        "new_call_since": new_call_since,
    }


@router.get("/todo")
def todo():
    tz = BUSINESS_TZ.key
    with db_connection() as conn:
        attention = [to_item(r) for r in conn.execute(ATTENTION).fetchall()]
        call_back = [to_call_back_item(r) for r in conn.execute(CALL_BACK).fetchall()]
        calls_today = conn.execute(CALLS_TODAY, (tz, tz)).fetchone()[0]
        sync_problems = conn.execute(SYNC_PROBLEMS).fetchone()[0]
    return {
        "attention": attention,
        "call_back": call_back,
        "summary": {
            "calls_today": calls_today,
            "hot_waiting": sum(1 for row in call_back if row["applicant"]["temperature"] == "HOT"),
            "to_call": len(call_back),
            "sync_problems": sync_problems,
        },
    }
