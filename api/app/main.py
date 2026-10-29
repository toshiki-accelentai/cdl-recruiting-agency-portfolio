import logging
from contextlib import asynccontextmanager

import psycopg
from fastapi import Depends, FastAPI, Response
from fastapi.responses import JSONResponse
from psycopg_pool import PoolTimeout
from psycopg.types.json import Jsonb

from app.api_key import require_api_key, require_internal_caller
from app.applicants import router as applicants_router
from app.auth import router as auth_router
from app.call_reports import router as call_reports_router
from app.caller_lookup import router as caller_lookup_router
from app.config import api_shared_secret, demo_config_problem
from app.corrections import router as corrections_router
from app.dashboard import router as dashboard_router
from app.db import close_pools, db_connection
from app.follow_up import router as follow_up_router
from app.helpers import classify_temperature, pick_phones
from app.logs import setup_logging, short
from app.pages import router as pages_router, static_files
from app.schemas import IntakeRequest
from app.todo import router as todo_router

setup_logging()
logger = logging.getLogger(__name__)

# docs_url, redoc_url and openapi_url are off: they list every endpoint, and this API is about to be public.
@asynccontextmanager
async def lifespan(_app):
    problem = demo_config_problem()
    if problem:
        raise RuntimeError(problem)  # a demo server must never start holding the n8n key or the VAPI key
    yield
    close_pools()  # hand the database connections back politely when the container stops


app = FastAPI(title="Frontline CDL intake API", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


@app.exception_handler(PoolTimeout)
async def pool_timeout(_request, _exc):
    """Every pooled connection was busy for the whole wait: say "try again", not a bare 500."""
    return JSONResponse({"detail": "busy, try again in a moment"}, status_code=503, headers={"Retry-After": "2"})


app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(corrections_router)
app.include_router(follow_up_router)
app.include_router(todo_router)
app.include_router(applicants_router)
app.include_router(call_reports_router)
app.include_router(caller_lookup_router)
app.include_router(pages_router)
app.mount("/static", static_files, name="static")

if not api_shared_secret():
    logger.warning("API_SHARED_SECRET is not set: POST /calls will answer 503 to every request")


# A field a recruiter has corrected (audit_log, action correct_applicant) is kept when the same phone calls again.
# Fields nobody corrected follow the newest call, and a blank answer never wipes anything. Temperature follows
# readiness, so a recruiter's change to either one keeps the temperature too. `locked` is a list of field names.
UPSERT_APPLICANT = """
INSERT INTO applicants (name, phone_e164, callback_phone, city, state, zip_code, experience, readiness, temperature)
VALUES (%(name)s, %(phone)s, %(callback)s, %(city)s, %(state)s, %(zip)s, %(experience)s, %(readiness)s, %(temperature)s)
ON CONFLICT (phone_e164) DO UPDATE SET
    name        = CASE WHEN 'name' = ANY(%(locked)s::text[]) THEN applicants.name
                       ELSE COALESCE(NULLIF(EXCLUDED.name, ''), applicants.name) END,
    callback_phone = COALESCE(NULLIF(EXCLUDED.callback_phone, ''), applicants.callback_phone),
    city        = CASE WHEN 'city' = ANY(%(locked)s::text[]) THEN applicants.city
                       ELSE COALESCE(NULLIF(EXCLUDED.city, ''), applicants.city) END,
    state       = CASE WHEN 'state' = ANY(%(locked)s::text[]) THEN applicants.state
                       ELSE COALESCE(NULLIF(EXCLUDED.state, ''), applicants.state) END,
    zip_code    = CASE WHEN 'zip_code' = ANY(%(locked)s::text[]) THEN applicants.zip_code
                       ELSE COALESCE(NULLIF(EXCLUDED.zip_code, ''), applicants.zip_code) END,
    experience  = CASE WHEN 'experience' = ANY(%(locked)s::text[]) THEN applicants.experience
                       ELSE COALESCE(NULLIF(EXCLUDED.experience, ''), applicants.experience) END,
    readiness   = CASE WHEN 'readiness' = ANY(%(locked)s::text[]) THEN applicants.readiness
                       ELSE COALESCE(NULLIF(EXCLUDED.readiness, ''), applicants.readiness) END,
    temperature = CASE WHEN 'temperature' = ANY(%(locked)s::text[]) OR 'readiness' = ANY(%(locked)s::text[])
                            THEN applicants.temperature
                       WHEN EXCLUDED.readiness <> '' THEN EXCLUDED.temperature
                       ELSE applicants.temperature END
RETURNING id, temperature
"""

# The fields a recruiter changed on the applicant who owns this phone, from the change history.
CORRECTED_FIELDS = """
SELECT DISTINCT field FROM audit_log al
JOIN applicants a ON a.id = al.applicant_id, jsonb_object_keys(al.changes) AS field
WHERE a.phone_e164 = %s AND al.action = 'correct_applicant'
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
            locked = [row[0] for row in conn.execute(CORRECTED_FIELDS, (phone,))]
            applicant_id, temperature = conn.execute(UPSERT_APPLICANT, {
                "name": args.name, "phone": phone, "callback": callback, "city": args.city, "state": args.state.upper(),
                "zip": args.zipCode, "experience": args.experience, "readiness": args.readiness,
                "temperature": classify_temperature(args.readiness) or "COLD",  # the column only allows 4 values
                "locked": locked,
            }).fetchone()
        row = conn.execute(
            "INSERT INTO calls (vapi_call_id, applicant_id, preferred_callback_at, raw_payload, "
            "needs_review, review_reason) VALUES (%s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (vapi_call_id) DO NOTHING RETURNING id",
            (vapi_call_id, applicant_id, args.preferredCallbackTime, Jsonb(payload),
             bool(reasons), ",".join(reasons) or None),
        ).fetchone()
        if row is None:
            # Either a replay (change nothing), or the end-of-call report got here first and made a
            # "no_intake" placeholder: then this intake completes that call instead of being dropped.
            placeholder = conn.execute(
                "SELECT id FROM calls WHERE vapi_call_id = %s "
                "AND review_reason = 'no_intake' FOR UPDATE", (vapi_call_id,)).fetchone()
            if placeholder is None:  # a real replay: undo the applicant upsert too
                duplicate = True
                raise psycopg.Rollback()
            conn.execute(
                "UPDATE calls SET applicant_id = %s, preferred_callback_at = %s, raw_payload = %s, "
                "needs_review = %s, review_reason = %s WHERE id = %s",
                (applicant_id, args.preferredCallbackTime, Jsonb(payload), bool(reasons),
                 ",".join(reasons) or None, placeholder[0]))
            row = placeholder
        call_id = row[0]
        if applicant_id is not None:  # nothing to sync for a call with no usable phone
            conn.execute(INSERT_OUTBOX, (call_id, applicant_id))
    if duplicate and args.preferredCallbackTime is not None:
        # A replay changes nothing, except the callback time: when the first time was rejected (weekend,
        # taken slot) the agent calls again in the same call with a new one, and the latest one is real.
        with conn.transaction():
            changed = conn.execute(
                "UPDATE calls SET preferred_callback_at = %s WHERE vapi_call_id = %s "
                "AND preferred_callback_at IS DISTINCT FROM %s RETURNING id",
                (args.preferredCallbackTime, vapi_call_id, args.preferredCallbackTime)).fetchone()
            if changed:
                # If the first time already reached Zoho, send again: the worker updates the same candidate
                # (known id, no duplicate) and adds a note with the new time. A send still pending reads the
                # latest time itself, and a failed one stays failed (it needs a person, not a new time).
                conn.execute("UPDATE outbox SET status = 'pending', attempts = 0, next_attempt_at = now(), "
                             "last_error = NULL, sent_at = NULL WHERE call_id = %s AND status = 'sent'",
                             (changed[0],))
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


@app.get("/healthz", include_in_schema=False)
def healthz():
    """For the container health check only: the process is up. It must not need the database."""
    return {"status": "ok"}


@app.post("/calls", status_code=201, dependencies=[Depends(require_internal_caller), Depends(require_api_key)])
def post_calls(req: IntakeRequest, response: Response):
    try:
        with db_connection() as conn:
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
