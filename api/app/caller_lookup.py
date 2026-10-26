"""GET /applicants/lookup: has this caller talked to us before? Asked by n8n routing before it asks Zoho.

The database is the system of record, so a caller saved here but not yet copied to Zoho counts as existing
(owner decision 2026-10-23). The answer holds only what the Existing Lead agent needs: found, the name for the
greeting, and the details on file that the save tool requires (so a returning caller is not asked for them again).
It goes into the call's prompt and VAPI's logs, so it never carries the phone, ids, notes, temperature or history.
"""
from fastapi import APIRouter, Depends, HTTPException

from app.api_key import require_api_key, require_internal_caller
from app.db import db_connection
from app.helpers import normalize_phone

router = APIRouter(dependencies=[Depends(require_internal_caller), Depends(require_api_key)])


@router.get("/applicants/lookup")
def lookup_caller(phone: str = ""):
    e164 = normalize_phone(phone)
    if e164 is None:
        raise HTTPException(status_code=422, detail="phone must be a US or Canadian number")
    with db_connection() as conn:
        row = conn.execute("SELECT name, city, state, zip_code, experience, readiness FROM applicants "
                           "WHERE phone_e164 = %s", (e164,)).fetchone()
    name, city, state, zip_code, experience, readiness = row or ("",) * 6
    return {"found": row is not None, "name": name, "city": city, "state": state, "zipCode": zip_code,
            "experience": experience, "readiness": readiness}
