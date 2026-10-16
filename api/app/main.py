import hmac
import logging

import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Response
from psycopg.types.json import Jsonb

from app.auth import router as auth_router
from app.config import api_shared_secret, database_url
from app.corrections import router as corrections_router
from app.dashboard import router as dashboard_router
from app.db import connect_with_retry
from app.follow_up import router as follow_up_router
from app.helpers import classify_temperature, pick_phones
from app.logs import setup_logging, short
from app.schemas import IntakeRequest
from app.todo import router as todo_router

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="Frontline CDL intake API")
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(corrections_router)
app.include_router(follow_up_router)
app.include_router(todo_router)

if not api_shared_secret():
    logger.warning("API_SHARED_SECRET is not set: POST /calls will answer 503 to every request")


def require_api_key(x_api_key: str = Header(default="")) -> None:
    """Only n8n (which knows the shared secret) may save calls. Never open by default."""
    secret = api_shared_secret()
    if not secret:
        raise HTTPException(status_code=503, detail="api key not configured")
    # compare_digest takes the same time however many leading characters match
    if not hmac.compare_digest(x_api_key.encode(), secret.encode()):
        logger.warning("rejected request: missing or wrong X-API-Key")
        raise HTTPException(status_code=401, detail="invalid api key")


UPSERT_APPLICANT = """
INSERT INTO applicants (name, phone_e164, callback_phone, city, state, zip_code, experience, readiness, temperature)
VALUES (%(name)s, %(phone)s, %(callback)s, %(city)s, %(state)s, %(zip)s, %(experience)s, %(readiness)s, %(temperature)s)
ON CONFLICT (phone_e164) DO UPDATE SET
    name        = COALESCE(NULLIF(EXCLUDED.name, ''),        applicants.name),
    callback_phone = COALESCE(NULLIF(EXCLUDED.callback_phone, ''), applicants.callback_phone),
    city        = COALESCE(NULLIF(EXCLUDED.city, ''),        applicants.city),
    state       = COALESCE(NULLIF(EXCLUDED.state, ''),       applicants.state),
    zip_code    = COALESCE(NULLIF(EXCLUDED.zip_code, ''),    applicants.zip_code),
    experience  = COALESCE(NULLIF(EXCLUDED.experience, ''),  applicants.experience),
    readiness   = COALESCE(NULLIF(EXCLUDED.readiness, ''),   applicants.readiness),
    temperature = CASE WHEN EXCLUDED.readiness <> '' THEN EXCLUDED.temperature
                       ELSE applicants.temperature END
RETURNING id, temperature
"""


INSERT_OUTBOX = "INSERT INTO outbox (call_id, applicant_id) VALUES (%s, %s)"


def save_intake(conn: psycopg.Connection, payload: dict, req: IntakeRequest) -> dict:
    """Write applicant (if the phone is usable) + call atomically.

    Never rejects a call over missing info: flag it for review instead. A replay of a
    known call id changes nothing.
    """
    args = req.message.toolCalls[0].function.arguments
    vapi_call_id = req.message.call.id
    caller_id = req.message.call.customer.number if req.message.call.customer else None
    phone, callback = pick_phones(caller_id, args.phoneNumber)
    reasons = (["invalid_phone"] if phone is None else []) + (["missing_name"] if not args.name else [])
    duplicate = False
    applicant_id = temperature = None
    with conn.transaction():
        if phone is not None:
            applicant_id, temperature = conn.execute(UPSERT_APPLICANT, {
                "name": args.name, "phone": phone, "callback": callback, "city": args.city, "state": args.state.upper(),
                "zip": args.zipCode, "experience": args.experience, "readiness": args.readiness,
                "temperature": classify_temperature(args.readiness),
            }).fetchone()
        row = conn.execute(
            "INSERT INTO calls (vapi_call_id, applicant_id, preferred_callback_at, raw_payload, "
            "needs_review, review_reason) VALUES (%s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (vapi_call_id) DO NOTHING RETURNING id",
            (vapi_call_id, applicant_id, args.preferredCallbackTime, Jsonb(payload),
             bool(reasons), ",".join(reasons) or None),
        ).fetchone()
        if row is None:  # call id already stored: undo the applicant upsert too
            duplicate = True
            raise psycopg.Rollback()
        call_id = row[0]
        if applicant_id is not None:  # nothing to sync for a call with no usable phone
            conn.execute(INSERT_OUTBOX, (call_id, applicant_id))
    if duplicate:
        call_id, applicant_id, temperature, needs_review = conn.execute(
            "SELECT c.id, c.applicant_id, a.temperature, c.needs_review FROM calls c "
            "LEFT JOIN applicants a ON a.id = c.applicant_id WHERE c.vapi_call_id = %s",
            (vapi_call_id,),
        ).fetchone()
    else:
        needs_review = bool(reasons)
    return {"call_id": call_id, "applicant_id": applicant_id, "temperature": temperature,
            "needs_review": needs_review, "duplicate": duplicate}


@app.post("/calls", status_code=201, dependencies=[Depends(require_api_key)])
def post_calls(req: IntakeRequest, response: Response):
    try:
        with connect_with_retry(database_url()) as conn:
            result = save_intake(conn, req.model_dump(mode="json"), req)
    except Exception as exc:  # re-raised: the 500 tells n8n "not saved". Log why, without caller data.
        logger.error("save failed %s: %s", type(exc).__name__, short(exc))
        raise
    if result["duplicate"]:
        response.status_code = 200
        logger.info("duplicate call call_id=%s", result["call_id"])
    else:
        logger.info("call saved call_id=%s applicant_id=%s needs_review=%s",
                    result["call_id"], result["applicant_id"], result["needs_review"])
    return result
