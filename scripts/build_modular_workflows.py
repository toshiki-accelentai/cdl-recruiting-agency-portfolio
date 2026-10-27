#!/usr/bin/env python3
"""Generate the single-responsibility CDL n8n workflow suite."""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path

try:
    from .build_production_workflow import (
        EXISTING_ASSISTANT_ID, NEW_ASSISTANT_ID, build as build_monolith, code, condition, connect, google_request,
        node, stable_id)
except ImportError:
    from build_production_workflow import (
        EXISTING_ASSISTANT_ID, NEW_ASSISTANT_ID, build as build_monolith, code, condition, connect, google_request,
        node, stable_id)


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
    for item in workflow["nodes"]:
        item["position"][0] -= 2080
        item["position"][1] += 80
        if item["name"] == "Validate Callback":
            item["parameters"]["jsCode"] = item["parameters"]["jsCode"].replace(
                "const intake = $('Resolve Candidate Result').first().json;",
                "const intake = $input.first().json;",
            )
    # The sub-workflow returns the output of whichever result node ran last; no pass-through end node needed.
    workflow["nodes"] = [trigger, *workflow["nodes"], *replace_previous_callback_nodes()]
    connect(workflow["connections"], "Booking Input", "Validate Callback")
    add_replace_previous_callback(workflow["connections"])
    return workflow


CALENDAR_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/toshiki%40accelentai.com/events"
# The booking answers a live tool call: these steps must be quick and may fail without failing the booking.
REPLACE_TIMEOUT_MS = 5000


def replace_previous_callback_nodes() -> list[dict]:
    """Owner decision 2026-10-27: one upcoming callback per phone number. After a confirmed booking, the caller's
    other upcoming callbacks (same callerPhone tag, our cdlslot ids) are cancelled. The new event is created first,
    so a failure here leaves two events (visible), never none (a lost callback)."""
    def quick_google(name, parameters, x, y):
        n = google_request(name, parameters, x, y)
        n["parameters"]["options"] = {"timeout": REPLACE_TIMEOUT_MS}
        n["retryOnFail"] = False
        n.pop("maxTries", None)
        n.pop("waitBetweenTries", None)
        return n
    booked = condition("Booked?", "={{ $json.status === 'booked' }}", 1920, 80)
    find = quick_google("Find Other Upcoming Callbacks", {
        "method": "GET",
        "url": CALENDAR_EVENTS_URL,
        "sendQuery": True,
        "queryParameters": {"parameters": [
            {"name": "privateExtendedProperty", "value": "=callerPhone={{ $json.phone }}"},
            {"name": "timeMin", "value": "={{ $now.toISO() }}"},
            {"name": "singleEvents", "value": "true"},
            {"name": "maxResults", "value": "20"},
        ]},
    }, 2180, 0)
    pick = code("Pick Callbacks to Replace", """
const booked = $('Build Booked Result').first().json;
const listing = $input.first().json;
if (listing.error || !Array.isArray(listing.items)) {
  return [{ json: { cancelId: null, searchFailed: Boolean(listing.error) } }];
}
// Only our own slot events for this exact phone, never the one just booked or one already cancelled.
const ids = listing.items
  .filter((e) => e.id !== booked.calendarEventId && e.status !== 'cancelled' && String(e.id).startsWith('cdlslot')
    && e.extendedProperties?.private?.callerPhone === booked.phone)
  .map((e) => e.id);
return ids.length ? ids.map((id) => ({ json: { cancelId: id } })) : [{ json: { cancelId: null, searchFailed: false } }];
""", 2440, 0, helpers=False)
    anything = condition("Anything to Replace?", "={{ Boolean($json.cancelId) }}", 2700, 0)
    cancel = quick_google("Cancel Replaced Callback", {
        "method": "DELETE",
        "url": "=" + CALENDAR_EVENTS_URL + "/{{ $json.cancelId }}",
        "sendQuery": True,
        "queryParameters": {"parameters": [{"name": "sendUpdates", "value": "none"}]},
    }, 2960, -80)
    finish = code("Finish Booking Result", """
const result = $('Build Booked Result').first().json;
const ran = (name) => { try { return $(name).all().map((i) => i.json); } catch (e) { return []; } };  // a skipped node throws
const picked = ran('Pick Callbacks to Replace');
const wanted = picked.filter((p) => p.cancelId);
const cancels = ran('Cancel Replaced Callback');
const replaced = cancels.filter((c) => !c.error).length;
const failed = picked.some((p) => p.searchFailed) || replaced < wanted.length;
return [{ json: { ...result, replacedPrevious: replaced, replaceFailed: failed } }];
""", 3220, 80, helpers=False)
    return [booked, find, pick, anything, cancel, finish]


def add_replace_previous_callback(connections: dict) -> None:
    connections["Build Booked Result"] = {"main": [[]]}
    connect(connections, "Build Booked Result", "Booked?")
    connect(connections, "Booked?", "Find Other Upcoming Callbacks", 0)
    connect(connections, "Booked?", "Finish Booking Result", 1)
    connect(connections, "Find Other Upcoming Callbacks", "Pick Callbacks to Replace")
    connect(connections, "Pick Callbacks to Replace", "Anything to Replace?")
    connect(connections, "Anything to Replace?", "Cancel Replaced Callback", 0)
    connect(connections, "Anything to Replace?", "Finish Booking Result", 1)
    connect(connections, "Cancel Replaced Callback", "Finish Booking Result")


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
    // On-file details the save tool requires; only the database has them (a Zoho-only caller is asked instead).
    city: fromDatabase ? db.city ?? '' : '',
    state: fromDatabase ? db.state ?? '' : '',
    zipCode: fromDatabase ? db.zipCode ?? '' : '',
    experience: fromDatabase ? db.experience ?? '' : '',
    readiness: fromDatabase ? db.readiness ?? '' : '',
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



RECRUITER_EMAIL = "toshiki@accelentai.com"
DASHBOARD_URL = "https://cdl-admin.accelentai.com"

_BUILD_RECRUITER_EMAIL_JS = r"""
// Runs after the caller has the answer. Same two emails as the client build: booked, or a person must book it.
// While the caller is still choosing a time (taken, outside hours, missing detail) nothing is sent.
const r = $input.first().json;
if (!['booked', 'manual_followup'].includes(r.status)) return [];
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const oneLine = (v) => String(v ?? '').replace(/[\r\n]+/g, ' ').trim();
const name = oneLine([r.firstName, r.lastName].filter(Boolean).join(' ')) || 'Unknown';
const where = `${r.city || ''}${r.state ? ', ' + r.state : ''}${r.zipCode ? ' ' + r.zipCode : ''}`.trim();
const when = r.startUtc
  ? new Date(r.startUtc).toLocaleString('en-US', { timeZone: 'America/Vancouver', weekday: 'short', month: 'short',
      day: 'numeric', hour: 'numeric', minute: '2-digit' }).replace(/ /g, ' ') + ' Pacific'
  : (r.preferredCallbackTime || 'not given');
const rows = [
  ['Name', name], ['Location', where], ['Phone', r.phone], ['Experience', r.experienceText],
  ['Readiness', r.readiness], ['Lead Temperature', r.temperature],
  [r.status === 'booked' ? 'Scheduled Callback Time' : 'Requested Callback Time', when],
].map(([k, v]) => `<b>${k}:</b> ${esc(v)}<br>`).join('\n');
const link = `Details:<br><a href="__DASHBOARD__">__DASHBOARD__</a><br><br>Thank you,<br>Recruiting Automation System`;
if (r.status === 'booked') {
  const n = Number(r.replacedPrevious) || 0;
  const moved = n > 0
    ? `<p>This booking replaces ${n} earlier callback${n === 1 ? '' : 's'} for the same phone number; the earlier calendar event was cancelled.</p>`
    : '';
  const warn = r.replaceFailed ? '<p><b>Check the calendar:</b> an earlier callback for this phone could not be cancelled.</p>' : '';
  return [{ json: {
    subject: `✅ Callback Appointment Scheduled with Lead ${name} ${oneLine(r.temperature)}`.trim() + (n > 0 ? ' (moved)' : ''),
    html: `A new driver lead has been received:<br><br>\n${rows}<br>\n${moved}${warn}${link}`,
  } }];
}
return [{ json: {
  subject: '⚠️ Appointment Booking Failed – Manual Action Required',
  html: `<p>Hi Team,</p><p>The system was unable to automatically create a callback appointment for the following lead.<br>
Please review the details and manually schedule a callback in your calendar at your earliest convenience.</p><hr>
<p><b>The lead details:</b></p>\n${rows}<br>\n${link}`,
} }];
""".replace("__DASHBOARD__", DASHBOARD_URL)


def add_recruiter_emails(workflow: dict, credential_id: str, credential_name: str) -> dict:
    """Return a copy of an Intake workflow that emails the recruiters after answering the caller.

    Restores the client build's two Gmail emails (booked; booking failed, manual action required). They hang off
    'Respond Booking Result', so the caller never waits for them, and a mail failure never fails the call record.
    The Gmail credential id is instance-local, so it is passed in, like the API key. Idempotent; touches no other
    node; used on the hand-edited live workflow.
    """
    patched = deepcopy(workflow)
    names = {n["name"] for n in patched["nodes"]}
    if "Email Recruiters" in names:
        return patched
    anchor = next((n for n in patched["nodes"] if n["name"] == "Respond Booking Result"), None)
    if anchor is None:
        raise ValueError("workflow has no 'Respond Booking Result' node")
    x, y = anchor["position"]
    build = code("Build Recruiter Email", _BUILD_RECRUITER_EMAIL_JS, x, y + 220, helpers=False)
    gmail = node(
        "Email Recruiters",
        "n8n-nodes-base.gmail",
        {"sendTo": RECRUITER_EMAIL, "subject": "={{ $json.subject }}", "emailType": "html",
         "message": "={{ $json.html }}", "options": {"appendAttribution": False}},
        x + 260, y + 220, 2.1,
        credentials={"gmailOAuth2": {"id": credential_id, "name": credential_name}},
        onError="continueRegularOutput",
    )
    patched["nodes"].extend([build, gmail])
    connections = patched["connections"]
    connections.setdefault("Respond Booking Result", {"main": [[]]})
    if not connections["Respond Booking Result"]["main"]:
        connections["Respond Booking Result"]["main"] = [[]]
    connections["Respond Booking Result"]["main"][0].append({"node": "Build Recruiter Email", "type": "main", "index": 0})
    connect(connections, "Build Recruiter Email", "Email Recruiters")
    return patched


_BUILD_CANCEL_EMAIL_JS = r"""
// Owner decision 2026-10-27: no cancel tool. A caller who still wants to cancel after being offered a move is only
// noted by the agent, so the recruiters are told here and decide. Sent only for calls labelled cancel_request.
const c = $input.first().json;
if (c.callIntent !== 'cancel_request') return [];
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
const oneLine = (v) => String(v ?? '').replace(/[\r\n]+/g, ' ').trim();
const name = oneLine(c.fullName) || 'Unknown caller';
const where = [c.city, c.state].filter(Boolean).join(', ') || 'not provided';
const rows = [['Name', name], ['Phone', c.phone], ['Location', where], ['VAPI call', c.callId]]
  .map(([k, v]) => `<b>${k}:</b> ${esc(v)}<br>`).join('\n');
return [{ json: {
  subject: `⚠️ Callback cancel request – ${name}`,
  html: `<p>Hi Team,</p><p>This driver said they want to cancel their callback, after the assistant offered to move it.</p>\n${rows}<br>
<p><b>What the call said:</b><br>${esc(c.summary) || 'No summary available.'}</p>
<p>Their calendar event was <b>not removed</b>. Please confirm with the driver, and remove the event if they confirm.</p>
Details:<br><a href="__DASHBOARD__">__DASHBOARD__</a><br><br>Thank you,<br>Recruiting Automation System`,
} }];
""".replace("__DASHBOARD__", DASHBOARD_URL)


def add_cancel_request_email(workflow: dict, credential_id: str, credential_name: str) -> dict:
    """Return a copy of a Post-Call workflow that emails the recruiters about a cancel request.

    Hangs off 'Normalize Post Call' as a side branch, so it does not need the Zoho lookup (a caller who is only in
    our database still gets reported) and cannot slow or break the note path. Idempotent; touches no other node.
    """
    patched = deepcopy(workflow)
    if any(n["name"] == "Email Recruiters About Cancel" for n in patched["nodes"]):
        return patched
    anchor = next((n for n in patched["nodes"] if n["name"] == "Normalize Post Call"), None)
    if anchor is None:
        raise ValueError("workflow has no 'Normalize Post Call' node")
    x, y = anchor["position"]
    build = code("Build Cancel Request Email", _BUILD_CANCEL_EMAIL_JS, x + 260, y + 260, helpers=False)
    gmail = node(
        "Email Recruiters About Cancel",
        "n8n-nodes-base.gmail",
        {"sendTo": RECRUITER_EMAIL, "subject": "={{ $json.subject }}", "emailType": "html",
         "message": "={{ $json.html }}", "options": {"appendAttribution": False}},
        x + 520, y + 260, 2.1,
        credentials={"gmailOAuth2": {"id": credential_id, "name": credential_name}},
        onError="continueRegularOutput",
    )
    patched["nodes"].extend([build, gmail])
    connections = patched["connections"]
    connections["Normalize Post Call"]["main"][0].append({"node": "Build Cancel Request Email", "type": "main", "index": 0})
    connect(connections, "Build Cancel Request Email", "Email Recruiters About Cancel")
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
