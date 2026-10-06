import psycopg
from fastapi import FastAPI, Response
from psycopg.types.json import Jsonb

from app.config import database_url
from app.helpers import classify_temperature, normalize_phone
from app.schemas import IntakeRequest

app = FastAPI(title="Frontline CDL intake API")


UPSERT_APPLICANT = """
INSERT INTO applicants (name, phone_e164, city, state, zip_code, experience, readiness, temperature)
VALUES (%(name)s, %(phone)s, %(city)s, %(state)s, %(zip)s, %(experience)s, %(readiness)s, %(temperature)s)
ON CONFLICT (phone_e164) DO UPDATE SET
    name        = COALESCE(NULLIF(EXCLUDED.name, ''),        applicants.name),
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
    phone = normalize_phone(args.phoneNumber)
    reasons = (["invalid_phone"] if phone is None else []) + (["missing_name"] if not args.name else [])
    duplicate = False
    applicant_id = temperature = None
    with conn.transaction():
        if phone is not None:
            applicant_id, temperature = conn.execute(UPSERT_APPLICANT, {
                "name": args.name, "phone": phone, "city": args.city, "state": args.state.upper(),
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


@app.post("/calls", status_code=201)
def post_calls(req: IntakeRequest, response: Response):
    with psycopg.connect(database_url()) as conn:
        result = save_intake(conn, req.model_dump(mode="json"), req)
    if result["duplicate"]:
        response.status_code = 200
    return result
