import psycopg
from fastapi import FastAPI, HTTPException
from psycopg.types.json import Jsonb

from app.config import database_url
from app.helpers import classify_temperature, normalize_phone
from app.schemas import IntakeRequest

app = FastAPI(title="Frontline CDL intake API")


def save_intake(conn: psycopg.Connection, payload: dict, req: IntakeRequest, phone: str) -> dict:
    """Write applicant + call atomically: both rows commit, or neither does."""
    args = req.message.toolCalls[0].function.arguments
    temperature = classify_temperature(args.readiness)
    with conn.transaction():
        applicant_id = conn.execute(
            "INSERT INTO applicants (name, phone_e164, city, state, zip_code, experience, readiness, temperature) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (args.name, phone, args.city, args.state.upper(), args.zipCode,
             args.experience, args.readiness, temperature),
        ).fetchone()[0]
        call_id = conn.execute(
            "INSERT INTO calls (vapi_call_id, applicant_id, preferred_callback_at, raw_payload) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (req.message.call.id, applicant_id, args.preferredCallbackTime, Jsonb(payload)),
        ).fetchone()[0]
    return {"call_id": call_id, "applicant_id": applicant_id, "temperature": temperature}


@app.post("/calls", status_code=201)
def post_calls(req: IntakeRequest):
    phone = normalize_phone(req.message.toolCalls[0].function.arguments.phoneNumber)
    if phone is None:
        raise HTTPException(status_code=422, detail="phoneNumber is not a valid US number")
    with psycopg.connect(database_url()) as conn:
        return save_intake(conn, req.model_dump(mode="json"), req, phone)
