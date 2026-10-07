#!/usr/bin/env python3
"""B1 smoke test: one fictional call -> local Postgres -> outbox worker -> REAL Zoho Recruit.

Real side effects with --apply: 1 Zoho Candidate (matched/created by the fictional phone) and
1 Note on it. Local dev database only (api/docker-compose.yml, port 5433). Without --apply it
prints the plan and touches nothing. Zoho credentials come from the repo-root .env.

    py -3.11 scripts/smoke_test_outbox_worker.py [--apply]
"""
from __future__ import annotations

import copy
import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))
sys.path.insert(0, str(ROOT / "scripts"))

PHONE = "2065550177"  # fictional (555-01xx)
NAME = "B1 Smoke Driver"


def main() -> None:
    apply = "--apply" in sys.argv
    print(f"plan: 1 fictional call ({NAME}, +1{PHONE}) -> local Postgres -> worker -> real Zoho "
          "(1 candidate + 1 note)")
    if not apply:
        print("dry run; pass --apply to run it")
        return

    from deploy_n8n_workflow import load_env
    os.environ.update({k: v for k, v in load_env().items() if k.startswith("ZOHO_")})
    os.environ.setdefault("DATABASE_URL", "postgresql://cdl:cdl@localhost:5433/cdl")

    import psycopg
    from fastapi.testclient import TestClient

    from app.config import database_url
    from app.main import app
    from app.migrate import migrate
    from app.worker import process_one, zoho_from_env

    migrate(database_url())
    fixture = ROOT / "docs/learning/existing/samples/u3-john-real-shape.json"
    payload = copy.deepcopy(json.loads(fixture.read_text(encoding="utf-8")))
    call_id = f"b1-smoke-{uuid.uuid4().hex[:8]}"
    payload["message"]["call"]["id"] = call_id
    payload["message"]["toolCalls"][0]["id"] = f"call_{call_id}"
    args = payload["message"]["toolCalls"][0]["function"]["arguments"]
    args.update(name=NAME, phoneNumber=PHONE, city="Seattle", state="WA", zipCode="98101",
                experience="2 years", readiness="within 3 days")
    response = TestClient(app).post("/calls", json=payload)
    print("POST /calls ->", response.status_code, response.json())

    zoho = zoho_from_env()
    with psycopg.connect(database_url()) as conn:
        while True:
            result = process_one(conn, zoho)
            print("worker ->", result)
            if result != "sent":
                break
        row = conn.execute(
            "SELECT o.status, o.attempts, o.last_error, a.zoho_candidate_id FROM outbox o "
            "JOIN calls c ON c.id = o.call_id JOIN applicants a ON a.id = o.applicant_id "
            "WHERE c.vapi_call_id = %s", (call_id,)).fetchone()
    print("outbox row (status, attempts, last_error, zoho_candidate_id):", row)
    print(f"check in Zoho Recruit: candidate '{NAME}' with a note titled 'VAPI Intake — {call_id}'")


if __name__ == "__main__":
    main()
