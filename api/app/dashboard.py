"""Read side of the recruiter dashboard: list calls (sort, filter, page) and show one call.

Login required (any role). Never returns raw_payload: that is VAPI's raw request, not for screens.
"""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import current_user
from app.exposure import for_user
from app.db import db_connection
from app.schemas import BUSINESS_TZ

router = APIRouter(prefix="/api", dependencies=[Depends(current_user)])

# The sort name chosen by the caller only ever selects one of these fixed strings; it is never
# pasted into the SQL itself.
ORDER_BY = {
    "newest": "c.created_at DESC, c.id DESC",
    "oldest": "c.created_at ASC, c.id ASC",
    "needs_review": "c.needs_review DESC, c.created_at DESC, c.id DESC",
    "temperature": (
        "CASE a.temperature WHEN 'HOT' THEN 0 WHEN 'MEDIUM' THEN 1 WHEN 'WARM' THEN 2 "
        "WHEN 'COLD' THEN 3 ELSE 4 END, c.created_at DESC, c.id DESC"
    ),
}

MAX_PAGE_SIZE = 200

SELECT_CALLS = """
SELECT c.id, c.created_at, c.preferred_callback_at, c.needs_review, c.review_reason,
       a.id, a.name, a.phone_e164, a.city, a.state, a.zip_code, a.experience, a.readiness,
       a.temperature, a.zoho_candidate_id,
       o.status, o.attempts, o.next_attempt_at, o.last_error, o.sent_at,
       a.follow_up_status, a.follow_up_note, a.follow_up_updated_at,
       c.summary, c.has_recording, c.caller_number,
       (a.follow_up_updated_at IS NOT NULL AND EXISTS (
            SELECT 1 FROM calls newer
            WHERE newer.applicant_id = a.id AND newer.created_at > a.follow_up_updated_at)
       ) AS new_call_since
FROM calls c
LEFT JOIN applicants a ON a.id = c.applicant_id
LEFT JOIN outbox o ON o.call_id = c.id
"""

# A hang-up: the call ended before the agent saved details, and the caller ID matches nobody (or there is none).
# Kept, but not a recruiter's problem: the Overview counts these instead of listing them.
HANG_UP = "(c.review_reason = 'no_intake' AND c.applicant_id IS NULL)"

FILTERS = """
WHERE (CAST(%(needs_review)s AS boolean) IS NULL OR c.needs_review = CAST(%(needs_review)s AS boolean))
  AND (CAST(%(kind)s AS text) IS NULL OR """ + HANG_UP + """)
  AND (CAST(%(sync)s AS text) IS NULL OR o.status = CAST(%(sync)s AS text))
  AND (CAST(%(follow_up)s AS text) IS NULL OR a.follow_up_status = CAST(%(follow_up)s AS text))
  AND (CAST(%(day)s AS text) IS NULL
       OR c.created_at >= date_trunc('day', now() AT TIME ZONE %(tz)s) AT TIME ZONE %(tz)s)
"""


def to_item(row: tuple) -> dict:
    (call_id, created_at, callback_at, needs_review, review_reason, applicant_id, name, phone, city,
     state, zip_code, experience, readiness, temperature, zoho_id,
     sync_status, attempts, next_attempt_at, last_error, sent_at,
     follow_up_status, follow_up_note, follow_up_updated_at, summary, has_recording, caller_number,
     new_call_since) = row
    return {
        "id": call_id,
        "created_at": created_at,
        "preferred_callback_at": callback_at,
        "needs_review": needs_review,
        "review_reason": review_reason,
        "summary": summary,  # the transcript is deliberately not here: it is large, and only the detail page needs it
        "has_recording": has_recording,
        "caller_number": caller_number,
        "applicant": None if applicant_id is None else {
            "id": applicant_id, "name": name, "phone": phone, "city": city, "state": state,
            "zip_code": zip_code, "experience": experience, "readiness": readiness,
            "temperature": temperature, "zoho_candidate_id": zoho_id, "has_zoho_record": zoho_id is not None,
            "follow_up": {"status": follow_up_status, "note": follow_up_note,
                          "updated_at": follow_up_updated_at, "new_call_since": new_call_since},
        },
        "sync": None if sync_status is None else {
            "status": sync_status, "attempts": attempts, "next_attempt_at": next_attempt_at,
            "last_error": last_error, "sent_at": sent_at,
        },
    }


@router.get("/calls")
def list_calls(
    sort: Literal["newest", "oldest", "needs_review", "temperature"] = "newest",
    needs_review: bool | None = None,
    sync: Literal["pending", "sent", "failed"] | None = None,
    follow_up: Literal["to_call", "called", "no_answer", "done"] | None = None,
    day: Literal["today"] | None = None,  # calls of the business day so far, the same rule as "calls today" on the Overview
    kind: Literal["hang_up"] | None = None,  # only the hang-ups the Overview leaves out of "Needs a closer look"
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    user: dict = Depends(current_user),
):
    params = {"needs_review": needs_review, "sync": sync, "follow_up": follow_up, "day": day, "kind": kind,
              "tz": BUSINESS_TZ.key, "limit": limit, "offset": offset}
    with db_connection() as conn:
        total = conn.execute(
            "SELECT count(*) FROM calls c LEFT JOIN applicants a ON a.id = c.applicant_id "
            "LEFT JOIN outbox o ON o.call_id = c.id" + FILTERS, params
        ).fetchone()[0]
        rows = conn.execute(
            SELECT_CALLS + FILTERS + f"ORDER BY {ORDER_BY[sort]} LIMIT %(limit)s OFFSET %(offset)s",
            params,
        ).fetchall()
    return for_user(user, {"items": [to_item(r) for r in rows], "total": total, "limit": limit, "offset": offset})


@router.get("/calls/{call_id}")
def get_call(call_id: int, user: dict = Depends(current_user)):
    with db_connection() as conn:
        row = conn.execute(SELECT_CALLS + "WHERE c.id = %s", (call_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="call not found")
    return for_user(user, to_item(row))
