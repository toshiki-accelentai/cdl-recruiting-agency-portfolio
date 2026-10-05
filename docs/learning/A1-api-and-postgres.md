# A1 — Python API + Postgres: receive an intake, save it atomically

> **Goal:** `POST /calls` takes the VAPI intake payload and saves the applicant
> and the call in Postgres, all-or-nothing.

## What it does

A VAPI-shaped body comes in (fixture:
`docs/learning/existing/samples/u3-john-real-shape.json`). The API validates it,
normalizes the phone to E.164, derives the lead temperature from `readiness`
(Python port of `cdl_helpers.js`), then writes two rows in one transaction.
It returns `201 {call_id, applicant_id, temperature}`. Bad phone or missing
name returns `422` and writes nothing.

## Data flow

```
VAPI body -> pydantic models (schemas.py) -> normalize_phone / classify_temperature (helpers.py)
          -> save_intake (main.py): BEGIN; INSERT applicants; INSERT calls; COMMIT
```

Files: `api/app/main.py` (endpoint + `save_intake`), `api/migrations/001_init.sql`
(schema), `api/app/migrate.py` (runner), `api/tests/` (real Postgres).

## Key design decisions

1. **One transaction, two tables.** `with conn.transaction():` wraps both inserts. If
   the second fails (`calls.vapi_call_id` is UNIQUE), the applicant row rolls back
   too. This is the base of the "no lead lost, no half-lead" story.
2. **`raw_payload jsonb` on every call.** Exactly what VAPI sent is kept, so the
   outbox worker (B1) and debugging never depend on what we chose to parse.
3. **Naive callback time = Vancouver time.** VAPI sends `2026-09-25T10:00:00` with no
   offset. The schema attaches `America/Vancouver` before it hits a `timestamptz`
   column (the U8 naive-vs-aware lesson, applied).
4. **Tests hit real Postgres**, not a mock: a mock can't prove a rollback.
5. **Plain `.sql` migrations + 20-line runner**, no Alembic: less to explain.

Not handled yet, on purpose (A2): a replayed call returns a raw DB error
(UNIQUE violation), and the same phone creates a second applicant.

## Run it

```bash
cd api
docker compose up -d db
.venv/Scripts/python.exe -m pytest -q          # 16 tests, real Postgres on :5433
.venv/Scripts/python.exe -m app.migrate        # apply migrations to the dev DB
.venv/Scripts/python.exe -m uvicorn app.main:app --reload
```

## Interview talking points

- "I split the write into two tables and wrapped them in one transaction, then
  wrote a test that forces the second insert to fail and checks the first one
  rolled back. I tested against real Postgres because a mock can't show that."
- "I kept the raw VAPI payload as jsonb, so the CRM sync can be rebuilt from our own
  database even if I change the parsing later."
- "I used AI to port the helper rules from JavaScript, then verified the port with
  the same cases, rather than trusting it."

## Debug drill

Done 2026-10-05 in a guided session (the `autocommit` bug breaks the rollback test). The patch was retired when A2 rewrote `save_intake`; the idea survives in the A2 rollback experiment.

## Glossary added
transaction (atomic write) · rollback · migration · UNIQUE constraint · foreign key ·
jsonb · autocommit
