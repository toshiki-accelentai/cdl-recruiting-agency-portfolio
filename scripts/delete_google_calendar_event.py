#!/usr/bin/env python3
"""Delete one explicitly identified Google Calendar event through n8n OAuth."""
from __future__ import annotations

import json
import sys
import urllib.request
import uuid

try:
    from .deploy_n8n_workflow import load_env, request
    from .smoke_test_google_calendar import http_node
except ImportError:
    from deploy_n8n_workflow import load_env, request
    from smoke_test_google_calendar import http_node


def main() -> None:
    if len(sys.argv) != 2 or not sys.argv[1].startswith("vapitest") and not sys.argv[1].startswith("vapivapitest"):
        raise SystemExit("pass one explicit smoke-test event ID")
    event_id = sys.argv[1]
    env = load_env()
    base = env["N8N_BASE_URL"].rstrip("/")
    key = env["N8N_API_KEY"]
    path = f"cdl/delete-smoke-event-{uuid.uuid4().hex[:16]}"
    url = f"https://www.googleapis.com/calendar/v3/calendars/toshiki%40accelentai.com/events/{event_id}"
    webhook = {
        "parameters": {"httpMethod": "POST", "path": path, "responseMode": "lastNode", "options": {}},
        "id": str(uuid.uuid4()), "name": "Cleanup Webhook", "type": "n8n-nodes-base.webhook",
        "typeVersion": 2.1, "position": [0, 0], "webhookId": str(uuid.uuid4()),
    }
    delete = http_node("Delete Smoke Event", "DELETE", url, [240, 0])
    workflow = {
        "name": f"TEMP - Delete calendar smoke event {event_id[-8:]}",
        "nodes": [webhook, delete],
        "connections": {"Cleanup Webhook": {"main": [[{"node": "Delete Smoke Event", "type": "main", "index": 0}]]}},
        "settings": {"executionOrder": "v1", "timezone": "America/Vancouver"},
    }
    workflow_id = None
    try:
        created = request("POST", f"{base}/api/v1/workflows", key, workflow)
        workflow_id = created["id"]
        request("POST", f"{base}/api/v1/workflows/{workflow_id}/activate", key)
        req = urllib.request.Request(f"{base}/webhook/{path}", data=b"{}", method="POST", headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=90) as response:
            response.read()
        print(json.dumps({"deleted": event_id}))
    finally:
        if workflow_id:
            try:
                request("POST", f"{base}/api/v1/workflows/{workflow_id}/deactivate", key)
            finally:
                request("DELETE", f"{base}/api/v1/workflows/{workflow_id}", key)


if __name__ == "__main__":
    main()
