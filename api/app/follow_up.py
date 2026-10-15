"""Follow-up tracking: one status per applicant (not per call), changed only by a logged-in recruiter.

Internal only: nothing here is queued for Zoho. Every real change is written to audit_log.
"""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

from app.auth import require_role
from app.config import database_url
from app.db import connect_with_retry

router = APIRouter(prefix="/api")

NOTE_MAX_LENGTH = 500


class FollowUpUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["to_call", "called", "no_answer", "done"] | None = None
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=NOTE_MAX_LENGTH)] | None = None

    @model_validator(mode="after")
    def something_to_change(self):
        if not self.model_fields_set:
            raise ValueError("send a status, a note, or both")
        return self


@router.patch("/applicants/{applicant_id}/follow-up")
def update_follow_up(applicant_id: int, update: FollowUpUpdate,
                     user: Annotated[dict, Depends(require_role("recruiter", "admin"))]):
    wanted = {"follow_up_status": update.status, "follow_up_note": update.note}
    with connect_with_retry(database_url()) as conn:
        with conn.transaction():
            row = conn.execute(
                "SELECT follow_up_status, follow_up_note, follow_up_updated_at FROM applicants "
                "WHERE id = %s FOR UPDATE", (applicant_id,)).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="applicant not found")
            current = {"follow_up_status": row[0], "follow_up_note": row[1]}
            changes = {col: {"from": current[col], "to": new}
                       for col, new in wanted.items() if new is not None and new != current[col]}
            updated_at = row[2]
            if changes:
                sets = {col: change["to"] for col, change in changes.items()}
                assignments = ", ".join(f"{col} = %({col})s" for col in sets)  # names come from `wanted` only
                updated_at = conn.execute(
                    f"UPDATE applicants SET {assignments}, follow_up_updated_at = now() "
                    "WHERE id = %(applicant_id)s RETURNING follow_up_updated_at",
                    {**sets, "applicant_id": applicant_id}).fetchone()[0]
                conn.execute("INSERT INTO audit_log (user_id, action, applicant_id, changes) "
                             "VALUES (%s, 'update_follow_up', %s, %s)",
                             (user["id"], applicant_id, Jsonb(changes)))
    final = {**current, **{col: change["to"] for col, change in changes.items()}}
    return {"status": final["follow_up_status"], "note": final["follow_up_note"],
            "updated_at": updated_at, "new_call_since": False}
