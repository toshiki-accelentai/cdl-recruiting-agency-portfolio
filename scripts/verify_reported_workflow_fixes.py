#!/usr/bin/env python3
"""Verify the published Intake booking-note and Post-Call note fixes.

Uses an existing synthetic Candidate, creates three diagnostic Notes through
the real public workflows, reads them back, then deletes those exact Note IDs.
It does not alter the active state of the four production workflows.
"""
from __future__ import annotations

import json
import time
import urllib.request
import uuid

try:
    from .build_production_workflow import code, connect, webhook, zoho_request
    from .deploy_n8n_workflow import deployable, load_env, request
except ImportError:
    from build_production_workflow import code, connect, webhook, zoho_request
    from deploy_n8n_workflow import deployable, load_env, request


PHONE = "+12025550111"
CALL_ID = "workflow-fix-verification-20260813"
POST_CALL_ID = f"{CALL_ID}-post-call"
EXPECTED_TITLES = {
    f"VAPI Intake — {CALL_ID}",
    f"Callback — {CALL_ID}",
    f"AI Call Summary & Full Transcript — {POST_CALL_ID}",
}


def call(url: str, body: dict) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=90) as response:
        raw = response.read().decode()
        return json.loads(raw) if raw.strip() else {"status": response.status}


def verification_workflow(path: str) -> dict:
    nodes = [
        webhook("Verify Fixes Webhook", path, 0, 0, response_mode="lastNode"),
        zoho_request("Find Synthetic Candidate", {
            "method": "GET",
            "url": "https://recruit.zoho.com/recruit/v2/Candidates/search",
            "sendQuery": True,
            "queryParameters": {"parameters": [
                {"name": "phone", "value": PHONE},
                {"name": "per_page", "value": "1"},
            ]},
        }, 240, 0),
        code("Capture Synthetic Candidate", """
const candidate = Array.isArray($json.data) ? $json.data[0] : null;
if (!candidate?.id) throw new Error('synthetic_candidate_not_found');
return [{json:{candidateId:candidate.id,candidateName:candidate.Full_Name}}];
""", 500, 0, helpers=False),
        zoho_request("Read Candidate Notes", {
            "method": "GET",
            "url": "=https://recruit.zoho.com/recruit/v2/Candidates/{{ $json.candidateId }}/Notes",
            "sendQuery": True,
            "queryParameters": {"parameters": [{"name": "per_page", "value": "100"}]},
        }, 760, 0),
        code("Report Fix Notes", f"""
const expected = {json.dumps(sorted(EXPECTED_TITLES), ensure_ascii=False)};
const notes = (Array.isArray($json.data) ? $json.data : [])
  .filter(note => expected.length === 0 || expected.includes(String(note.Note_Title ?? '')))
  .map(note => ({{id:String(note.id),title:note.Note_Title,content:String(note.Note_Content ?? '')}}));
return [{{json:{{notes,foundTitles:notes.map(note => note.title),complete:expected.every(title => notes.some(note => note.title === title))}}}}];
""", 1020, 0, helpers=False),
    ]
    connections = {}
    for left, right in zip(nodes, nodes[1:]):
        connect(connections, left["name"], right["name"])
    return {
        "name": "TEMP - Verify Reported Workflow Fixes",
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1", "timezone": "America/Vancouver"},
    }


def cleanup_workflow(path: str, note_ids: list[str]) -> dict:
    ids = ",".join(note_ids)
    nodes = [
        webhook("Cleanup Fix Notes Webhook", path, 0, 0, response_mode="lastNode"),
        zoho_request("Delete Exact Fix Notes", {
            "method": "DELETE",
            "url": f"https://recruit.zoho.com/recruit/v2/Notes?ids={ids}&wf_trigger=false",
        }, 260, 0),
        code("Verify Fix Notes Deleted", f"""
const records = Array.isArray($json.data) ? $json.data : [];
const expected = {json.dumps(note_ids)};
const deleted = records.filter(record => record?.code === 'SUCCESS').map(record => String(record.details?.id));
if (!expected.every(id => deleted.includes(id))) throw new Error('diagnostic_note_cleanup_failed');
return [{{json:{{deleted}}}}];
""", 520, 0, helpers=False),
    ]
    connections = {}
    connect(connections, nodes[0]["name"], nodes[1]["name"])
    connect(connections, nodes[1]["name"], nodes[2]["name"])
    return {
        "name": "TEMP - Cleanup Reported Workflow Fix Notes",
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1", "timezone": "America/Vancouver"},
    }


def temporary_call(base: str, key: str, workflow: dict, path: str, body: dict | None = None) -> dict:
    created = request("POST", f"{base}/api/v1/workflows", key, deployable(workflow))
    workflow_id = created["id"]
    try:
        request("POST", f"{base}/api/v1/workflows/{workflow_id}/activate", key)
        return call(f"{base}/webhook/{path}", body or {})
    finally:
        try:
            request("POST", f"{base}/api/v1/workflows/{workflow_id}/deactivate", key)
        finally:
            request("DELETE", f"{base}/api/v1/workflows/{workflow_id}", key)


def main() -> None:
    env = load_env()
    base = env["N8N_BASE_URL"].rstrip("/")
    key = env["N8N_API_KEY"]
    suffix = uuid.uuid4().hex[:16]

    intake = call(f"{base}/webhook/cdl/log-applicant", {"message": {
        "call": {"id": CALL_ID, "customer": {"number": PHONE}},
        "toolCalls": [{
            "id": "workflow-fix-intake-tool",
            "type": "function",
            "function": {"name": "logApplicantInfo", "arguments": {
                "name": "Marcus Thompson",
                "readiness": "within 3 days",
                "experience": "5+ years",
                "phoneNumber": PHONE,
                "city": "Tacoma",
                "state": "WA",
                "zipCode": "98402",
                "preferredCallbackTime": "2026-08-15T10:00:00-07:00",
            }},
        }],
    }})
    post_call = call(f"{base}/webhook/cdl/post-call", {"message": {
        "call": {"id": POST_CALL_ID, "customer": {"number": PHONE}},
        "artifact": {"transcript": "Synthetic regression verification transcript."},
        "analysis": {"summary": "Verified the corrected post-call Note path."},
        "endedReason": "customer-ended-call",
        "durationSeconds": 42,
        "cost": 0.01,
    }})

    verify_path = f"cdl/verify-reported-fixes-{suffix}"
    verified = {}
    for _ in range(10):
        verified = temporary_call(base, key, verification_workflow(verify_path), verify_path)
        if verified.get("complete"):
            break
        time.sleep(1)
        verify_path = f"cdl/verify-reported-fixes-{uuid.uuid4().hex[:16]}"

    if not verified.get("complete"):
        raise RuntimeError(f"reported workflow fixes not verified: {verified}")

    note_ids = [note["id"] for note in verified["notes"]]
    cleanup_path = f"cdl/cleanup-reported-fixes-{uuid.uuid4().hex[:16]}"
    cleanup = temporary_call(base, key, cleanup_workflow(cleanup_path, note_ids), cleanup_path)
    print(json.dumps({
        "intakeResponse": intake,
        "postCallResponse": post_call,
        "verifiedNotes": verified["notes"],
        "cleanup": cleanup,
    }, indent=2))


if __name__ == "__main__":
    main()
