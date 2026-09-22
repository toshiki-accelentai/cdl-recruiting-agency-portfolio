#!/usr/bin/env python3
"""Smoke-test each inactive modular CDL workflow without persistent test data."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

try:
    from .deploy_n8n_workflow import load_env, request
    from .smoke_test_google_calendar import GOOGLE_CREDENTIAL, http_node
except ImportError:
    from deploy_n8n_workflow import load_env, request
    from smoke_test_google_calendar import GOOGLE_CREDENTIAL, http_node


WORKFLOWS = {
    "routing": "fqfDmPbJQzhHE7Bf",
    "intake": "CrGEvZ5vuX37rshi",
    "booking": "nIqItEX8Vbn78sWo",
    "post_call": "XGMOFG1hROutdkCF",
}


def base32hex_number(value: int) -> str:
    alphabet = "0123456789abcdefghijklmnopqrstuv"
    if value == 0:
        return "0"
    encoded = ""
    while value:
        value, remainder = divmod(value, 32)
        encoded = alphabet[remainder] + encoded
    return encoded


def call(url: str, body: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=90) as response:
        return json.loads(response.read().decode())


def activate(base: str, key: str, workflow_id: str) -> None:
    request("POST", f"{base}/api/v1/workflows/{workflow_id}/activate", key)


def deactivate(base: str, key: str, workflow_id: str) -> None:
    request("POST", f"{base}/api/v1/workflows/{workflow_id}/deactivate", key)


def next_test_slot() -> tuple[str, str]:
    local = datetime.now(ZoneInfo("America/Vancouver")) + timedelta(days=370)
    while local.weekday() >= 5:
        local += timedelta(days=1)
    local = local.replace(hour=10, minute=0, second=0, microsecond=0)
    return local.astimezone(timezone.utc).isoformat(), (local + timedelta(minutes=15)).astimezone(timezone.utc).isoformat()


def booking_caller(path: str, event_id: str, start: str, end: str) -> dict:
    calendar_event_id = f"cdlslot{base32hex_number(int(datetime.fromisoformat(start).timestamp()))}"
    event_url = f"https://www.googleapis.com/calendar/v3/calendars/toshiki%40accelentai.com/events/{calendar_event_id}"
    nodes = [
        {
            "parameters": {"httpMethod": "POST", "path": path, "responseMode": "lastNode", "options": {}},
            "id": str(uuid.uuid4()), "name": "Test Webhook", "type": "n8n-nodes-base.webhook",
            "typeVersion": 2.1, "position": [0, 0], "webhookId": str(uuid.uuid4()),
        },
        {
            "parameters": {"jsCode": f"""
return [{{json:{{
  candidateId:'test-candidate', candidateSaved:true, toolCallId:'test-tool-call',
  callId:'{event_id}', phone:'+19995550123', firstName:'Calendar', lastName:'SmokeTest',
  city:'Vancouver', state:'WA', zipCode:'98660', experienceText:'2+ years',
  experienceYears:2, readiness:'within 7 days', temperature:'HOT',
  preferredCallbackTime:'{start}'
}}}}];
"""},
            "id": str(uuid.uuid4()), "name": "Prepare Booking", "type": "n8n-nodes-base.code",
            "typeVersion": 2, "position": [240, 0],
        },
        {
            "parameters": {
                "workflowId": {"__rl": True, "value": WORKFLOWS["booking"], "mode": "list", "cachedResultName": "CDL 03 - Calendar Booking"},
                "workflowInputs": {"mappingMode": "defineBelow", "value": {}, "matchingColumns": [], "schema": [], "attemptToConvertTypes": False, "convertFieldsToString": True},
                "mode": "each", "options": {"waitForSubWorkflow": True},
            },
            "id": str(uuid.uuid4()), "name": "Execute Booking", "type": "n8n-nodes-base.executeWorkflow",
            "typeVersion": 1.2, "position": [480, 0], "alwaysOutputData": True,
            "onError": "continueRegularOutput",
        },
        {
            "parameters": {"jsCode": "return [{json:{...$json,smokeBooked:$json.booked===true,smokeEventId:$json.calendarEventId??''}}];"},
            "id": str(uuid.uuid4()), "name": "Capture Result", "type": "n8n-nodes-base.code",
            "typeVersion": 2, "position": [720, 0],
        },
        http_node("Delete Event", "DELETE", event_url, [960, 0]),
        http_node("Confirm Deleted", "GET", event_url, [1200, 0]),
        {
            "parameters": {"jsCode": f"""
const result=$('Capture Result').first().json;
const after=$json;
const deleted=Boolean(after.error||[404,410].includes(after.statusCode)||after.status==='cancelled'||String(after.message??'').toLowerCase().includes('not found'));
return [{{json:{{booked:result.smokeBooked,eventIdMatches:result.smokeEventId==='{calendar_event_id}',deletionConfirmed:deleted,diagnostic:result}}}}];
"""},
            "id": str(uuid.uuid4()), "name": "Report", "type": "n8n-nodes-base.code",
            "typeVersion": 2, "position": [1440, 0],
        },
    ]
    connections = {}
    for left, right in zip(nodes, nodes[1:]):
        connections[left["name"]] = {"main": [[{"node": right["name"], "type": "main", "index": 0}]]}
    return {
        "name": f"TEMP - Modular booking smoke {event_id[-8:]}", "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1", "timezone": "America/Vancouver"},
    }


def test_public_workflow(base: str, key: str, workflow_id: str, path: str, payload: dict) -> dict:
    activate(base, key, workflow_id)
    try:
        return call(f"{base}/webhook/{path}", payload)
    finally:
        deactivate(base, key, workflow_id)


def main() -> None:
    env = load_env()
    base = env["N8N_BASE_URL"].rstrip("/")
    key = env["N8N_API_KEY"]
    results = {}
    results["routing"] = test_public_workflow(
        base, key, WORKFLOWS["routing"], "cdl/assistant-request",
        {"message": {"call": {"customer": {"number": "+19995550123"}}}},
    )
    activate(base, key, WORKFLOWS["booking"])
    try:
        results["invalid_intake"] = test_public_workflow(
            base, key, WORKFLOWS["intake"], "cdl/log-applicant",
            {"message": {"toolCalls": []}},
        )
        results["post_call"] = test_public_workflow(
            base, key, WORKFLOWS["post_call"], "cdl/post-call",
            {"message": {"call": {"id": "smoke-no-write", "customer": {"number": "+19995550123"}}}},
        )

        suffix = uuid.uuid4().hex[:20]
        event_id = f"vapitest{suffix}"
        start, end = next_test_slot()
        path = f"cdl/modular-booking-smoke-{suffix}"
        temporary = booking_caller(path, event_id, start, end)
        workflow_id = None
        try:
            created = request("POST", f"{base}/api/v1/workflows", key, temporary)
            workflow_id = created["id"]
            activate(base, key, workflow_id)
            results["booking"] = call(f"{base}/webhook/{path}", {})
        finally:
            if workflow_id:
                try:
                    deactivate(base, key, workflow_id)
                finally:
                    request("DELETE", f"{base}/api/v1/workflows/{workflow_id}", key)
    finally:
        deactivate(base, key, WORKFLOWS["booking"])

    checks = {
        "routing": bool(results["routing"].get("assistantId")),
        "invalid_intake": "results" in results["invalid_intake"],
        "post_call": results["post_call"].get("received") is True,
        "booking": all(results["booking"].get(key) is True for key in ("booked", "eventIdMatches", "deletionConfirmed")),
    }
    print(json.dumps(checks, indent=2))
    if not all(checks.values()):
        print(json.dumps(results, indent=2)[:8000])
        raise RuntimeError("modular smoke test failed")


if __name__ == "__main__":
    main()
