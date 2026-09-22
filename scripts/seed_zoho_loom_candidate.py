#!/usr/bin/env python3
"""Create/update one fictional Loom demo Candidate through the real intake flow.

Dry-run by default. Pass --apply to write the Candidate and demo Notes. The
chosen callback is a future Saturday, so no Calendar event is created.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

try:
    from .build_production_workflow import code, connect, webhook, zoho_request
    from .deploy_n8n_workflow import deployable, load_env, request
except ImportError:
    from build_production_workflow import code, connect, webhook, zoho_request
    from deploy_n8n_workflow import deployable, load_env, request


INTAKE_ID = "CrGEvZ5vuX37rshi"
BOOKING_ID = "nIqItEX8Vbn78sWo"
PHONE = "+12025550197"
CALL_ID = "loom-demo-candidate-20260812"


def callback_time() -> str:
    value = datetime.now(ZoneInfo("America/Vancouver")) + timedelta(days=1)
    while value.weekday() != 5:
        value += timedelta(days=1)
    return value.replace(hour=10, minute=0, second=0, microsecond=0).isoformat()


def payload() -> dict:
    return {
        "message": {
            "call": {"id": CALL_ID, "customer": {"number": PHONE}},
            "toolCalls": [{
                "id": "loom-demo-tool-call",
                "type": "function",
                "function": {
                    "name": "logApplicantInfo",
                    "arguments": {
                        "name": "Loom Demo Candidate",
                        "readiness": "within 7 days",
                        "experience": "2+ years",
                        "phoneNumber": PHONE,
                        "city": "Vancouver",
                        "state": "WA",
                        "zipCode": "98660",
                        "preferredCallbackTime": callback_time(),
                    },
                },
            }],
        }
    }


def call(url: str, body: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as response:
        raw = response.read().decode()
        if not raw.strip():
            raise RuntimeError(f"n8n returned an empty response (HTTP {response.status})")
        return json.loads(raw)


def verification_workflow(path: str) -> dict:
    nodes = [
        webhook("Verify Webhook", path, 0, 0, response_mode="lastNode"),
        zoho_request("Find Loom Candidate", {
            "method": "GET",
            "url": "https://recruit.zoho.com/recruit/v2/Candidates/search",
            "sendQuery": True,
            "queryParameters": {"parameters": [
                {"name": "phone", "value": PHONE},
                {"name": "per_page", "value": "1"},
            ]},
        }, 240, 0),
        code("Capture Loom Candidate", """
const candidate = Array.isArray($json.data) ? $json.data[0] : null;
if (!candidate?.id) throw new Error('loom_demo_candidate_not_found');
return [{json:{candidateId:candidate.id,candidate:{
  id:candidate.id, First_Name:candidate.First_Name, Last_Name:candidate.Last_Name,
  Phone:candidate.Phone, City:candidate.City, State:candidate.State,
  Zip_Code:candidate.Zip_Code, Experience_in_Years:candidate.Experience_in_Years,
  Source:candidate.Source,
}}}];
""", 500, 0, helpers=False),
        zoho_request("Get Loom Candidate Notes", {
            "method": "GET",
            "url": "=https://recruit.zoho.com/recruit/v2/Candidates/{{ $json.candidateId }}/Notes",
            "sendQuery": True,
            "queryParameters": {"parameters": [{"name": "per_page", "value": "50"}]},
        }, 760, 0),
        code("Report Loom Candidate", f"""
const candidate = $('Capture Loom Candidate').first().json.candidate;
const notes = (Array.isArray($json.data) ? $json.data : [])
  .filter(note => String(note.Note_Title ?? '').includes('{CALL_ID}'))
  .map(note => ({{id:note.id,title:note.Note_Title}}));
const hasIntakeNote = notes.some(note => note.title.startsWith('VAPI Intake'));
const hasBookingNote = notes.some(note => note.title.startsWith('Callback'));
return [{{json:{{candidate,notes,noteCount:notes.length,hasIntakeNote,hasBookingNote}}}}];
""", 1020, 0, helpers=False),
    ]
    connections = {}
    for left, right in zip(nodes, nodes[1:]):
        connect(connections, left["name"], right["name"])
    return {"name": "TEMP - Verify Loom Zoho Candidate", "nodes": nodes, "connections": connections, "settings": {"executionOrder": "v1", "timezone": "America/Vancouver"}}


def main() -> None:
    sample = payload()
    print(json.dumps(sample["message"]["toolCalls"][0]["function"]["arguments"], indent=2))
    verify_only = "--verify-only" in sys.argv
    if "--apply" not in sys.argv and not verify_only:
        print("dry run; pass --apply to create/update the fictional Candidate")
        return

    env = load_env()
    base = env["N8N_BASE_URL"].rstrip("/")
    key = env["N8N_API_KEY"]
    path = f"cdl/verify-loom-candidate-{uuid.uuid4().hex[:16]}"
    verifier_id = None
    if not verify_only:
        request("POST", f"{base}/api/v1/workflows/{BOOKING_ID}/activate", key)
        request("POST", f"{base}/api/v1/workflows/{INTAKE_ID}/activate", key)
    try:
        intake_result = None if verify_only else call(f"{base}/webhook/cdl/log-applicant", sample)
        verifier = request("POST", f"{base}/api/v1/workflows", key, deployable(verification_workflow(path)))
        verifier_id = verifier["id"]
        request("POST", f"{base}/api/v1/workflows/{verifier_id}/activate", key)
        verified = {}
        for _ in range(6):
            verified = call(f"{base}/webhook/{path}", {})
            if verified.get("hasIntakeNote") and verified.get("hasBookingNote"):
                break
            time.sleep(1)
        result = {"verified": verified}
        if intake_result is not None:
            result["intakeResult"] = intake_result
        print(json.dumps(result, indent=2))
        if (
            not verified.get("candidate", {}).get("id")
            or not verified.get("hasIntakeNote")
            or not verified.get("hasBookingNote")
        ):
            raise RuntimeError("Candidate or expected demo Notes were not verified")
    finally:
        if verifier_id:
            try:
                request("POST", f"{base}/api/v1/workflows/{verifier_id}/deactivate", key)
            finally:
                request("DELETE", f"{base}/api/v1/workflows/{verifier_id}", key)
        if not verify_only:
            request("POST", f"{base}/api/v1/workflows/{INTAKE_ID}/deactivate", key)
            request("POST", f"{base}/api/v1/workflows/{BOOKING_ID}/deactivate", key)


if __name__ == "__main__":
    main()
