"""Recruiter corrections: PATCH /api/calls/{id} fixes the applicant behind a call.

Every real change is audited (who, what, old -> new) and queued in the outbox so the worker updates
Zoho. A phone that already belongs to another applicant is rejected, never silently merged.
"""
from typing import Annotated, Literal

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator, model_validator

from app.auth import require_writer
from app.exposure import for_user
from app.dashboard import SELECT_CALLS, to_item
from app.db import db_connection
from app.helpers import classify_temperature, normalize_phone

router = APIRouter(prefix="/api")

Text100 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]

# request field -> applicants column (a fixed map: request keys never reach the SQL text)
COLUMNS = {"name": "name", "phone": "phone_e164", "city": "city", "state": "state",
           "zip_code": "zip_code", "experience": "experience", "readiness": "readiness",
           "temperature": "temperature"}


class CallCorrection(BaseModel):
    model_config = ConfigDict(extra="forbid")  # temperature, ids, etc. cannot be set from outside

    name: Text100 | None = None
    phone: str | None = None
    city: Text100 | None = None
    state: Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[A-Za-z]{2}$")] | None = None
    zip_code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10)] | None = None
    experience: Text100 | None = None
    readiness: Text100 | None = None
    # Derived from readiness at intake, but a recruiter who phoned the applicant knows better.
    temperature: Literal["HOT", "MEDIUM", "WARM", "COLD"] | None = None

    @field_validator("phone")
    @classmethod
    def usable_phone(cls, v: str | None) -> str | None:
        if v is None:
            return None
        phone = normalize_phone(v)
        if phone is None:
            raise ValueError("not a usable US phone number")
        return phone

    @field_validator("state")
    @classmethod
    def upper_state(cls, v: str | None) -> str | None:
        return v.upper() if v else v

    @model_validator(mode="after")
    def something_to_change(self):
        if not self.model_fields_set:
            raise ValueError("send at least one field to change")
        return self


def _current_applicant(conn: psycopg.Connection, applicant_id: int) -> dict:
    cols = list(COLUMNS.values())
    row = conn.execute(f"SELECT {', '.join(cols)} FROM applicants WHERE id = %s FOR UPDATE",
                       (applicant_id,)).fetchone()
    return dict(zip(cols, row))


def _correct_existing(conn, user_id: int, call_id: int, applicant_id: int, fields: dict) -> None:
    current = _current_applicant(conn, applicant_id)
    changes = {name: {"from": current[col], "to": fields[name]}
               for name, col in COLUMNS.items() if name in fields and fields[name] != current[col]}
    if not changes:
        return
    if "phone" in changes:
        owner = conn.execute("SELECT id, name FROM applicants WHERE phone_e164 = %s AND id <> %s",
                             (fields["phone"], applicant_id)).fetchone()
        if owner:
            raise HTTPException(status_code=409, detail={
                "message": "that phone number already belongs to another applicant",
                "existing_applicant": {"id": owner[0], "name": owner[1]}})
    sets = {COLUMNS[name]: change["to"] for name, change in changes.items()}
    if "readiness" in changes and "temperature" not in fields:  # an explicit temperature wins
        new_temperature = classify_temperature(fields["readiness"])
        if new_temperature != current["temperature"]:
            sets["temperature"] = new_temperature
            changes["temperature"] = {"from": current["temperature"], "to": new_temperature}
    assignments = ", ".join(f"{col} = %({col})s" for col in sets)  # column names come from COLUMNS only
    conn.execute(f"UPDATE applicants SET {assignments} WHERE id = %(applicant_id)s",
                 {**sets, "applicant_id": applicant_id})
    audit_id = conn.execute(
        "INSERT INTO audit_log (user_id, action, call_id, applicant_id, changes) "
        "VALUES (%s, 'correct_applicant', %s, %s, %s) RETURNING id",
        (user_id, call_id, applicant_id, Jsonb(changes))).fetchone()[0]
    conn.execute("INSERT INTO outbox (kind, applicant_id, audit_id) VALUES ('correction', %s, %s)",
                 (applicant_id, audit_id))


def _attach_applicant(conn, user_id: int, call_id: int, fields: dict) -> tuple[int, bool]:
    """Give a call with no applicant one: reuse the applicant that owns this phone, else create it."""
    if "phone" not in fields:
        raise HTTPException(status_code=422, detail="this call has no applicant yet: send a phone number")
    created = conn.execute(
        "INSERT INTO applicants (name, phone_e164, city, state, zip_code, experience, readiness, "
        "temperature) VALUES (%(name)s, %(phone)s, %(city)s, %(state)s, %(zip_code)s, %(experience)s, "
        "%(readiness)s, %(temperature)s) ON CONFLICT (phone_e164) DO NOTHING RETURNING id",
        {"name": "", "city": "", "state": "", "zip_code": "", "experience": "", "readiness": "",
         "temperature": classify_temperature(fields.get("readiness", "")), **fields}).fetchone()
    if created:
        applicant_id, created_new = created[0], True
    else:  # the phone already has an applicant: attach to it and leave its data alone
        applicant_id = conn.execute("SELECT id FROM applicants WHERE phone_e164 = %s",
                                    (fields["phone"],)).fetchone()[0]
        created_new = False
    conn.execute("UPDATE calls SET applicant_id = %s WHERE id = %s", (applicant_id, call_id))
    conn.execute("INSERT INTO outbox (call_id, applicant_id) VALUES (%s, %s)", (call_id, applicant_id))
    changes = {"attached_applicant_id": applicant_id, "created_new_applicant": created_new}
    if created_new:
        changes["fields"] = fields
    conn.execute("INSERT INTO audit_log (user_id, action, call_id, applicant_id, changes) "
                 "VALUES (%s, 'attach_applicant', %s, %s, %s)",
                 (user_id, call_id, applicant_id, Jsonb(changes)))
    return applicant_id, created_new


def _refresh_review_flag(conn, call_id: int, applicant_id: int) -> None:
    """A flagged call stays flagged only for reasons that are still true."""
    name = conn.execute("SELECT name FROM applicants WHERE id = %s", (applicant_id,)).fetchone()[0]
    reasons = ["missing_name"] if not name else []
    conn.execute("UPDATE calls SET needs_review = %s, review_reason = %s WHERE id = %s",
                 (bool(reasons), ",".join(reasons) or None, call_id))


@router.patch("/calls/{call_id}")
def correct_call(call_id: int, correction: CallCorrection,
                 user: Annotated[dict, Depends(require_writer)]):
    fields = correction.model_dump(exclude_none=True)
    attached_to_existing = False
    with db_connection() as conn:
        with conn.transaction():  # all or nothing: a 409 or 422 below undoes everything above it
            row = conn.execute("SELECT applicant_id, needs_review FROM calls WHERE id = %s FOR UPDATE",
                               (call_id,)).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="call not found")
            applicant_id, flagged = row
            if applicant_id is None:
                applicant_id, created_new = _attach_applicant(conn, user["id"], call_id, fields)
                attached_to_existing = not created_new
            else:
                _correct_existing(conn, user["id"], call_id, applicant_id, fields)
            if flagged:
                _refresh_review_flag(conn, call_id, applicant_id)
        item = to_item(conn.execute(SELECT_CALLS + "WHERE c.id = %s", (call_id,)).fetchone())
    return for_user(user, {**item, "attached_to_existing": attached_to_existing})
