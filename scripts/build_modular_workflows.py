#!/usr/bin/env python3
"""Generate the single-responsibility CDL n8n workflow suite."""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path

try:
    from .build_production_workflow import build as build_monolith, code, connect, node
except ImportError:
    from build_production_workflow import build as build_monolith, code, connect, node


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "config" / "n8n" / "production" / "modular"
BOOKING_PLACEHOLDER = "BOOKING_WORKFLOW_ID_REQUIRED"
# Python intake API on hermes-vps, reachable only over the private n8n_app Docker network.
INTAKE_API_URL = "http://cdl-api:8000/calls"

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
    workflow = subset(source, ROUTING, "CDL 01 - Assistant Routing", "routing")
    for item in workflow["nodes"]:
        item["position"][1] += 600
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
