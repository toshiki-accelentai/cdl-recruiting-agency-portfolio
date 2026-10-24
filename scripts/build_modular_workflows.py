#!/usr/bin/env python3
"""Generate the single-responsibility CDL n8n workflow suite."""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path

try:
    from .build_production_workflow import (
        EXISTING_ASSISTANT_ID, NEW_ASSISTANT_ID, build as build_monolith, code, condition, connect, node, stable_id)
except ImportError:
    from build_production_workflow import (
        EXISTING_ASSISTANT_ID, NEW_ASSISTANT_ID, build as build_monolith, code, condition, connect, node, stable_id)


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "config" / "n8n" / "production" / "modular"
BOOKING_PLACEHOLDER = "BOOKING_WORKFLOW_ID_REQUIRED"
# Python intake API on hermes-vps, reachable only over the private n8n_app Docker network.
INTAKE_API_URL = "http://cdl-api:8000/calls"
LOOKUP_API_URL = "http://cdl-api:8000/applicants/lookup"
# VAPI fails the call if assistant-request is not answered within 7.5 s (fixed). Database + Zoho must fit inside it.
ROUTING_DATABASE_TIMEOUT_MS = 2000
ROUTING_ZOHO_TIMEOUT_MS = 4000

FILES = {
    "routing": "cdl-01-assistant-routing.json",
    "intake": "cdl-02-applicant-intake.json",
    "booking": "cdl-03-calendar-booking.json",
    "post_call": "cdl-04-post-call-report.json",
}

ROUTING = {
    "Route Caller Webhook", "Normalize Route Request", "Find Candidate for Routing",
    "Build Assistant Response", "Respond Route",
}
INTAKE = {
    "Applicant Intake Webhook", "Normalize Intake", "Intake Valid?", "Respond Invalid Intake",
    "Find Candidate for Intake", "Build Candidate Write Request", "Write Candidate",
    "Resolve Candidate Result", "Candidate Saved?", "Respond Candidate Failure", "Add Intake Note",
    "Respond Booking Result", "Add Booking Note",
}
BOOKING = {
    "Validate Callback", "Callback Valid?", "Build Non-Booking Result",
    "Check Calendar Availability", "Assess Availability", "Calendar Slot Free?",
    "Build Calendar Event", "Create Calendar Event", "Confirm Calendar Event",
    "Calendar Event Cancelled?", "Restore Cancelled Slot", "Confirm Restored Slot",
    "Build Booked Result",
}
POST_CALL = {
    "Post Call Webhook", "Acknowledge Post Call", "Normalize Post Call",
    "Find Candidate for Post Call", "Build Post Call Note", "Post Call Candidate Found?",
    "Add Post Call Note",
}


def settings() -> dict:
    return {
        "executionOrder": "v1",
        "timezone": "America/Vancouver",
        "saveDataErrorExecution": "all",
        "saveDataSuccessExecution": "none",
        "saveManualExecutions": True,
        "saveExecutionProgress": False,
    }


def subset(source: dict, names: set[str], name: str, key: str) -> dict:
    nodes = [deepcopy(item) for item in source["nodes"] if item["name"] in names]
    connections: dict = {}
    for source_name, outputs in source["connections"].items():
        if source_name not in names:
            continue
        kept = []
        for branch in outputs.get("main", []):
            kept.append([edge for edge in deepcopy(branch) if edge["node"] in names])
        if any(kept):
            connections[source_name] = {"main": kept}
    return {
        "name": name,
        "nodes": nodes,
        "connections": connections,
        "settings": settings(),
        "active": False,
        "tags": [],
        "meta": {"managedBy": "scripts/build_modular_workflows.py", "component": key, "version": 1},
    }


def build_booking(source: dict) -> dict:
    workflow = subset(source, BOOKING, "CDL 03 - Calendar Booking", "booking")
    trigger = node(
        "Booking Input",
        "n8n-nodes-base.executeWorkflowTrigger",
        {"inputSource": "passthrough"},
        0,
        0,
        1.1,
    )
    terminal = code(
        "Return Booking Result",
        "return $input.all();",
        3360,
        0,
        helpers=False,
    )
    for item in workflow["nodes"]:
        item["position"][0] -= 2080
        item["position"][1] += 80
        if item["name"] == "Validate Callback":
            item["parameters"]["jsCode"] = item["parameters"]["jsCode"].replace(
                "const intake = $('Resolve Candidate Result').first().json;",
                "const intake = $input.first().json;",
            )
    workflow["nodes"] = [trigger, *workflow["nodes"], terminal]
    connect(workflow["connections"], "Booking Input", "Validate Callback")
    connect(workflow["connections"], "Build Booked Result", "Return Booking Result")
    connect(workflow["connections"], "Build Non-Booking Result", "Return Booking Result")
    return workflow


def build_routing(source: dict) -> dict:
    """Database first, Zoho only when the database does not know the caller (owner decision 2026-10-23:
    an existing caller is anyone who has talked to us, even before the worker copied them to Zoho)."""
    workflow = subset(source, ROUTING, "CDL 01 - Assistant Routing", "routing")
    for item in workflow["nodes"]:
        item["position"][1] += 600
        if item["name"] == "Find Candidate for Routing":
            item["parameters"]["options"]["timeout"] = ROUTING_ZOHO_TIMEOUT_MS
            item["retryOnFail"] = False  # 3 tries x 4 s would blow the 7.5 s budget; a miss just means "new caller"
            item.pop("maxTries", None)
            item.pop("waitBetweenTries", None)
            item["position"] = [1020, 120]
        if item["name"] == "Build Assistant Response": item["position"] = [1280, 0]
        if item["name"] == "Respond Route": item["position"] = [1540, 0]
    # The API key is an instance-local n8n "Header Auth" credential, attached at deploy time.
    lookup = node(
        "Find Applicant in Database",
        "n8n-nodes-base.httpRequest",
        {
            "method": "GET",
            "url": LOOKUP_API_URL,
            "authentication": "genericCredentialType",
            "genericAuthType": "httpHeaderAuth",
            "sendQuery": True,
            "queryParameters": {"parameters": [
                {"name": "phone", "value": "={{ $('Normalize Route Request').first().json.phone || '' }}"},
            ]},
            "options": {"timeout": ROUTING_DATABASE_TIMEOUT_MS},
        },
        500, 0, 4.4,
        alwaysOutputData=True,
        onError="continueRegularOutput",  # API down or 422 -> fall through to Zoho, never fail the call
    )
    found = condition("Found in Database?", "={{ $json.found === true }}", 760, 0)
    respond = code("Build Assistant Response", f"""
const route = $('Normalize Route Request').first().json;
const db = $('Find Applicant in Database').first().json ?? {{}};
const fromDatabase = Boolean(route.valid && db.found === true);
const candidate = !fromDatabase && Array.isArray($json.data) ? $json.data[0] : null;
const fromZoho = Boolean(route.valid && candidate?.id);
const existing = fromDatabase || fromZoho;
return [{{ json: {{
  assistantId: existing ? '{EXISTING_ASSISTANT_ID}' : '{NEW_ASSISTANT_ID}',
  assistantOverrides: {{ variableValues: {{
    phoneNumber: route.phone ?? '',
    name: fromDatabase ? db.name : fromZoho ? [candidate.First_Name, candidate.Last_Name].filter(Boolean).join(' ') : '',
  }} }},
  routing: fromDatabase ? 'existing_database' : fromZoho ? 'existing_candidate' : 'new_candidate',
}} }}];
""", 1280, 0, helpers=False)
    workflow["nodes"] = [n for n in workflow["nodes"] if n["name"] != "Build Assistant Response"] + [lookup, found, respond]
    connections = workflow["connections"]
    connections["Normalize Route Request"] = {"main": [[]]}
    connect(connections, "Normalize Route Request", "Find Applicant in Database")
    connect(connections, "Find Applicant in Database", "Found in Database?")
    connect(connections, "Found in Database?", "Build Assistant Response", 0)
    connect(connections, "Found in Database?", "Find Candidate for Routing", 1)
    return workflow


def execute_booking_node(booking_workflow_id: str) -> dict:
    return node(
        "Execute Calendar Booking",
        "n8n-nodes-base.executeWorkflow",
        {
            "workflowId": {
                "__rl": True,
                "value": booking_workflow_id,
                "mode": "list",
                "cachedResultName": "CDL 03 - Calendar Booking",
            },
            "workflowInputs": {
                "mappingMode": "defineBelow",
                "value": {},
                "matchingColumns": [],
                "schema": [],
                "attemptToConvertTypes": False,
                "convertFieldsToString": True,
            },
            "mode": "each",
            "options": {"waitForSubWorkflow": True},
        },
        2320,
        -80,
        1.2,
        alwaysOutputData=True,
        onError="continueRegularOutput",
    )


def add_save_to_api_branch(workflow: dict) -> dict:
    """Return a copy of an Intake workflow with the raw-body -> Python API side branch.

    Fan-out from the webhook: the new node is the first edge (executionOrder v1 runs branches one
    after another) and has no outgoing edges, so it cannot alter what Normalize Intake receives.
    onError=continue keeps an API failure away from the live call; retries are safe because the
    API is idempotent. Idempotent itself, and touches nothing else (used on the hand-edited live
    workflow as well as in the generated one).
    """
    patched = deepcopy(workflow)
    if any(n["name"] == "Save to Database API" for n in patched["nodes"]):
        return patched
    anchor = next(n for n in patched["nodes"] if n["name"] == "Normalize Intake")
    patched["nodes"].append(node(
        "Save to Database API",
        "n8n-nodes-base.httpRequest",
        {
            "method": "POST",
            "url": INTAKE_API_URL,
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify($json.body) }}",
            "options": {"timeout": 4000},
        },
        anchor["position"][0],
        anchor["position"][1] - 260,
        4.4,
        retryOnFail=True,
        maxTries=2,
        waitBetweenTries=1000,
        onError="continueRegularOutput",
    ))
    patched["connections"]["Applicant Intake Webhook"]["main"][0].insert(
        0, {"node": "Save to Database API", "type": "main", "index": 0})
    return patched


def add_api_key_auth(workflow: dict, credential_id: str, credential_name: str) -> dict:
    """Return a copy of an Intake workflow whose 'Save to Database API' node sends the API key.

    The key lives in an n8n "Header Auth" credential (name X-API-Key), never in the workflow JSON.
    The credential id is instance-local, so it is passed in, not stored in the generated suite.
    Changes only that node; idempotent; used on the hand-edited live workflow.
    """
    patched = deepcopy(workflow)
    node_ = next((n for n in patched["nodes"] if n["name"] == "Save to Database API"), None)
    if node_ is None:
        raise ValueError("workflow has no 'Save to Database API' node")
    node_["parameters"]["authentication"] = "genericCredentialType"
    node_["parameters"]["genericAuthType"] = "httpHeaderAuth"
    node_["credentials"] = {"httpHeaderAuth": {"id": credential_id, "name": credential_name}}
    return patched


ZOHO_WRITER_NODES = frozenset({
    "Find Candidate for Intake", "Build Candidate Write Request", "Write Candidate",
    "Resolve Candidate Result", "Candidate Saved?", "Respond Candidate Failure",
    "Add Intake Note", "Add Booking Note", "Verify Booking Note",
})

_PREPARE_BOOKING_INPUT_JS = """
// Database-first: Zoho is written only by the outbox worker, never from this workflow.
// Booking needs just the normalized intake; the candidate may not exist in Zoho yet.
return [{json: {...$('Normalize Intake').first().json, candidateId: ''}}];
"""


def make_database_first(workflow: dict) -> dict:
    """Return a copy of an Intake workflow in which the outbox worker is the only Zoho writer.

    Before this, n8n and the worker both wrote Zoho for the same call and created two candidates.
    Removes the candidate, intake-note and booking-note nodes, and points the booking path at the
    normalized intake instead. The caller is answered from the booking result, so a Zoho outage no
    longer turns into "manual follow-up" on the phone. Idempotent; used on the hand-edited live
    workflow (only the two nodes that read the removed ones are changed, hand edits elsewhere stay).
    The Callback note (booking outcome in Zoho) is not written any more: follow-up in tasks/todo.md.
    """
    patched = deepcopy(workflow)
    patched["nodes"] = [n for n in patched["nodes"] if n["name"] not in ZOHO_WRITER_NODES]
    connections = {}
    for source, outputs in patched["connections"].items():
        if source in ZOHO_WRITER_NODES:
            continue
        kept = [[e for e in output if e["node"] not in ZOHO_WRITER_NODES] for output in outputs["main"]]
        if any(kept):
            connections[source] = {**outputs, "main": kept}
    patched["connections"] = connections
    # The valid branch used to lead into Find Candidate for Intake; it now goes straight to booking.
    connections["Intake Valid?"]["main"][0] = [
        {"node": "Prepare Booking Input", "type": "main", "index": 0}]
    for n in patched["nodes"]:
        if n["name"] == "Prepare Booking Input":
            n["parameters"]["jsCode"] = _PREPARE_BOOKING_INPUT_JS
        elif n["name"] == "Normalize Booking Outcome":
            n["parameters"]["jsCode"] = n["parameters"]["jsCode"].replace(
                "$('Resolve Candidate Result')", "$('Prepare Booking Input')")
    return patched


def require_database_save(workflow: dict) -> dict:
    """Return a copy of an Intake workflow that books and says 'saved' only if the DB save worked.

    The Save to Database API node is a side branch with onError=continue, so a failed save used to
    be invisible: the booking path ran on and told the caller their details were saved. Now a valid
    intake passes through 'Saved to Database?' first; if the API returned no call id the caller is
    told a recruiter will follow up manually. The save is the webhook's first edge, so it has
    finished by the time the check runs. Idempotent; leaves every existing node untouched.
    """
    patched = deepcopy(workflow)
    if any(n["name"] == "Saved to Database?" for n in patched["nodes"]):
        return patched
    valid = next(n for n in patched["nodes"] if n["name"] == "Intake Valid?")
    x, y = valid["position"]
    patched["nodes"].append(node(
        "Saved to Database?",
        "n8n-nodes-base.if",
        {"conditions": {
            "options": {"caseSensitive": True, "typeValidation": "strict", "version": 2},
            "conditions": [{
                "id": stable_id("condition:Saved to Database?"),
                "leftValue": "={{ Boolean($('Save to Database API').first().json.call_id) }}",
                "rightValue": "",
                "operator": {"type": "boolean", "operation": "true", "singleValue": True},
            }],
            "combinator": "and"}, "options": {}},
        x + 260, y - 40, 2.2))
    patched["nodes"].append(node(
        "Respond Save Failure",
        "n8n-nodes-base.respondToWebhook",
        {"respondWith": "json",
         "responseBody": ("={{ {results:[{toolCallId:$json.toolCallId,result:JSON.stringify("
                          "{status:'manual_followup',saved:false,booked:false,message:'I could not "
                          "save your details automatically. A recruiter will follow up with you "
                          "manually.',callId:$json.callId})}]} }}"),
         "options": {"responseCode": 200,
                     "responseHeaders": {"entries": [{"name": "Content-Type", "value": "application/json"}]}}},
        x + 520, y + 180, 1.4))
    connections = patched["connections"]
    connections["Intake Valid?"]["main"][0] = []  # was: straight into the booking path
    connect(connections, "Intake Valid?", "Saved to Database?", 0)
    connect(connections, "Saved to Database?", "Prepare Booking Input", 0)
    connect(connections, "Saved to Database?", "Respond Save Failure", 1)
    return patched


def build_intake(source: dict, booking_workflow_id: str) -> dict:
    workflow = subset(source, INTAKE, "CDL 02 - Applicant Intake", "intake")
    execute = execute_booking_node(booking_workflow_id)
    prepare = code("Prepare Booking Input", """
const record = Array.isArray($json.data) ? $json.data[0] : null;
if ($json.error || record?.code !== 'SUCCESS') {
  throw new Error(`intake_note_write_failed: ${$json.message ?? record?.message ?? 'unknown'}`);
}
return [{json: $('Resolve Candidate Result').first().json}];
""", 2190, -80, helpers=False)
    normalize = code("Normalize Booking Outcome", """
const candidate = $('Resolve Candidate Result').first().json;
const result = $input.first().json;
if (result.status && typeof result.booked === 'boolean') return [{json: result}];
return [{json:{
  ...candidate,
  status:'manual_followup', booked:false, calendarUrl:'', calendarEventId:'',
  bookingReason:'booking_subworkflow_failed',
  callerMessage:'Your application was saved, but the calendar could not be confirmed. A recruiter will follow up manually.',
}}];
""", 2580, -80, helpers=False)
    verify = code("Verify Booking Note", """
const record = Array.isArray($json.data) ? $json.data[0] : null;
if ($json.error || (record?.code && record.code !== 'SUCCESS')) {
  throw new Error(`booking_note_write_failed: ${$json.message ?? record?.message ?? 'unknown'}`);
}
return $input.all();
""", 3360, -80, helpers=False)
    for item in workflow["nodes"]:
        if item["name"] == "Respond Booking Result": item["position"] = [2840, -80]
        if item["name"] == "Add Booking Note": item["position"] = [3100, -80]
    workflow["nodes"].extend([prepare, execute, normalize, verify])
    connect(workflow["connections"], "Add Intake Note", "Prepare Booking Input")
    connect(workflow["connections"], "Prepare Booking Input", "Execute Calendar Booking")
    connect(workflow["connections"], "Execute Calendar Booking", "Normalize Booking Outcome")
    connect(workflow["connections"], "Normalize Booking Outcome", "Respond Booking Result")
    connect(workflow["connections"], "Add Booking Note", "Verify Booking Note")
    return add_save_to_api_branch(workflow)


def build_post_call(source: dict) -> dict:
    workflow = subset(source, POST_CALL, "CDL 04 - Post-Call Report", "post_call")
    for item in workflow["nodes"]:
        item["position"][1] -= 600
    verify = code("Verify Post-Call Note", """
const record = Array.isArray($json.data) ? $json.data[0] : null;
if ($json.error || (record?.code && record.code !== 'SUCCESS')) {
  throw new Error(`post_call_note_write_failed: ${$json.message ?? record?.message ?? 'unknown'}`);
}
return $input.all();
""", 1280, 0, helpers=False)
    workflow["nodes"].append(verify)
    connect(workflow["connections"], "Add Post Call Note", "Verify Post-Call Note")
    return workflow


def build_suite(booking_workflow_id: str = BOOKING_PLACEHOLDER) -> dict[str, dict]:
    source = build_monolith()
    return {
        "routing": build_routing(source),
        "intake": build_intake(source, booking_workflow_id),
        "booking": build_booking(source),
        "post_call": build_post_call(source),
    }


def write_suite(suite: dict[str, dict]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for key, workflow in suite.items():
        path = OUT_DIR / FILES[key]
        path.write_text(json.dumps(workflow, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)} ({len(workflow['nodes'])} nodes)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--booking-workflow-id", default=BOOKING_PLACEHOLDER)
    args = parser.parse_args()
    write_suite(build_suite(args.booking_workflow_id))


if __name__ == "__main__":
    main()
