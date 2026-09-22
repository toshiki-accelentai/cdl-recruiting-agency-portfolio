#!/usr/bin/env python3
"""Delete one exact Zoho Recruit Note through the saved n8n OAuth credential.

Dry-run by default. This is intended for cleaning known test artifacts only.
"""
from __future__ import annotations

import json
import sys
import urllib.request
import uuid

try:
    from .build_production_workflow import code, connect, webhook, zoho_request
    from .deploy_n8n_workflow import deployable, load_env, request
except ImportError:
    from build_production_workflow import code, connect, webhook, zoho_request
    from deploy_n8n_workflow import deployable, load_env, request


def workflow(path: str, note_id: str) -> dict:
    nodes = [
        webhook("Delete Note Webhook", path, 0, 0, response_mode="lastNode"),
        zoho_request("Delete Exact Zoho Note", {
            "method": "DELETE",
            "url": f"https://recruit.zoho.com/recruit/v2/Notes/{note_id}",
            "sendQuery": True,
            "queryParameters": {"parameters": [{"name": "wf_trigger", "value": "false"}]},
        }, 260, 0),
        code("Verify Exact Note Deleted", f"""
const record = Array.isArray($json.data) ? $json.data[0] : null;
if (record?.code !== 'SUCCESS' || String(record?.details?.id) !== '{note_id}') {{
  throw new Error(`note_delete_failed: ${{$json.message ?? record?.message ?? 'unknown'}}`);
}}
return [{{json:{{deleted:true,noteId:String(record.details.id)}}}}];
""", 520, 0, helpers=False),
    ]
    connections = {}
    connect(connections, nodes[0]["name"], nodes[1]["name"])
    connect(connections, nodes[1]["name"], nodes[2]["name"])
    return {
        "name": "TEMP - Delete Exact Zoho Demo Note",
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1", "timezone": "America/Vancouver"},
    }


def call(url: str) -> dict:
    req = urllib.request.Request(
        url,
        data=b"{}",
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=90) as response:
        return json.loads(response.read().decode())


def main() -> None:
    if len(sys.argv) < 2 or not sys.argv[1].isdigit():
        raise SystemExit("usage: delete_zoho_note.py NOTE_ID [--apply]")
    note_id = sys.argv[1]
    print(json.dumps({"noteId": note_id, "action": "delete exact Zoho Recruit demo Note"}))
    if "--apply" not in sys.argv:
        print("dry run; pass --apply to delete the exact Note")
        return

    env = load_env()
    base = env["N8N_BASE_URL"].rstrip("/")
    key = env["N8N_API_KEY"]
    path = f"cdl/delete-demo-note-{uuid.uuid4().hex[:16]}"
    created = request("POST", f"{base}/api/v1/workflows", key, deployable(workflow(path, note_id)))
    workflow_id = created["id"]
    try:
        request("POST", f"{base}/api/v1/workflows/{workflow_id}/activate", key)
        print(json.dumps(call(f"{base}/webhook/{path}"), indent=2))
    finally:
        try:
            request("POST", f"{base}/api/v1/workflows/{workflow_id}/deactivate", key)
        finally:
            request("DELETE", f"{base}/api/v1/workflows/{workflow_id}", key)


if __name__ == "__main__":
    main()
