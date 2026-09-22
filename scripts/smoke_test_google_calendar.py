#!/usr/bin/env python3
"""Run an isolated Google Calendar create/read/delete test through n8n.

The script creates a temporary n8n webhook workflow, activates only that test
workflow, creates a clearly labelled future event, reads it back, deletes it,
confirms it is no longer retrievable, and removes the temporary workflow.
"""
from __future__ import annotations

import json
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

from deploy_n8n_workflow import load_env, request


CALENDAR_ID = "toshiki@accelentai.com"
GOOGLE_CREDENTIAL = {"id": "1sf9UUIeS6G5wyhc", "name": "Google Calendar account"}


def http_node(name: str, method: str, url: str, position: list[int], **parameters) -> dict:
    return {
        "parameters": {
            "method": method,
            "url": url,
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "googleCalendarOAuth2Api",
            "options": {"timeout": 10000},
            **parameters,
        },
        "id": str(uuid.uuid4()),
        "name": name,
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.4,
        "position": position,
        "credentials": {"googleCalendarOAuth2Api": GOOGLE_CREDENTIAL},
        "retryOnFail": True,
        "maxTries": 3,
        "waitBetweenTries": 1000,
        "onError": "continueRegularOutput",
        "alwaysOutputData": True,
    }


def build_workflow(path: str, event_id: str, start: str, end: str) -> dict:
    event_body = json.dumps({
        "id": event_id,
        "summary": "DELETE ME - n8n Google credential smoke test",
        "description": "Automated integration test; deleted in the same execution.",
        "start": {"dateTime": start, "timeZone": "America/Vancouver"},
        "end": {"dateTime": end, "timeZone": "America/Vancouver"},
    })
    event_url = f"https://www.googleapis.com/calendar/v3/calendars/toshiki%40accelentai.com/events/{event_id}"
    nodes = [
        {
            "parameters": {"httpMethod": "POST", "path": path, "responseMode": "lastNode", "options": {}},
            "id": str(uuid.uuid4()),
            "name": "Smoke Webhook",
            "type": "n8n-nodes-base.webhook",
            "typeVersion": 2.1,
            "position": [0, 0],
            "webhookId": str(uuid.uuid4()),
        },
        {
            "parameters": {"jsCode": f"return [{{json:{{eventId:'{event_id}',start:'{start}',end:'{end}'}}}}];"},
            "id": str(uuid.uuid4()),
            "name": "Prepare Test",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [240, 0],
        },
        http_node(
            "FreeBusy",
            "POST",
            "https://www.googleapis.com/calendar/v3/freeBusy",
            [480, 0],
            sendBody=True,
            specifyBody="json",
            jsonBody="={{ JSON.stringify({timeMin:$json.start,timeMax:$json.end,timeZone:'America/Vancouver',items:[{id:'toshiki@accelentai.com'}]}) }}",
        ),
        {
            "parameters": {"jsCode": f"return [{{json:{{eventBody:{event_body}}}}}];"},
            "id": str(uuid.uuid4()),
            "name": "Build Event Body",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [600, 0],
        },
        http_node(
            "Create Event",
            "POST",
            "https://www.googleapis.com/calendar/v3/calendars/toshiki%40accelentai.com/events",
            [840, 0],
            sendBody=True,
            specifyBody="json",
            jsonBody="={{ JSON.stringify($json.eventBody) }}",
        ),
        http_node(
            "Get Event",
            "GET",
            event_url,
            [960, 0],
        ),
        http_node(
            "Delete Event",
            "DELETE",
            event_url,
            [1200, 0],
        ),
        http_node(
            "Confirm Deleted",
            "GET",
            event_url,
            [1440, 0],
        ),
        {
            "parameters": {
                "jsCode": """
const prepared = $('Prepare Test').first().json;
const freeBusy = $('FreeBusy').first().json;
const created = $('Create Event').first().json;
const fetched = $('Get Event').first().json;
const afterDelete = $('Confirm Deleted').first().json;
const deletionConfirmed = Boolean(
  afterDelete.error ||
  [404, 410].includes(afterDelete.statusCode) ||
  String(afterDelete.message ?? '').includes('not found') ||
  String(afterDelete.message ?? '').includes('deleted') ||
  afterDelete.status === 'cancelled'
);
return [{json:{
  freeBusyOk:Boolean(freeBusy.calendars?.['toshiki@accelentai.com']),
  created:created.id === prepared.eventId,
  fetched:fetched.id === prepared.eventId,
  deletionConfirmed,
  eventId:prepared.eventId,
  createDiagnostic:created.error ?? created.message ?? created,
  createRaw:created,
  fetchDiagnostic:fetched.error ?? fetched.message ?? fetched,
  afterDelete,
}}];
"""
            },
            "id": str(uuid.uuid4()),
            "name": "Report",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1680, 0],
        },
    ]
    names = [node["name"] for node in nodes]
    connections = {
        names[index]: {"main": [[{"node": names[index + 1], "type": "main", "index": 0}]]}
        for index in range(len(names) - 1)
    }
    return {
        "name": f"TEMP - Google Calendar credential smoke {event_id[-8:]}",
        "nodes": nodes,
        "connections": connections,
        "settings": {"executionOrder": "v1", "timezone": "America/Vancouver"},
    }


def call_webhook(url: str) -> dict:
    req = urllib.request.Request(url, data=b"{}", method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as response:
        return json.loads(response.read().decode())


def main() -> None:
    env = load_env()
    base = env["N8N_BASE_URL"].rstrip("/")
    key = env["N8N_API_KEY"]
    suffix = uuid.uuid4().hex[:24]
    event_id = f"vapitest{suffix}"
    path = f"cdl/calendar-credential-smoke-{suffix}"
    start_dt = (datetime.now(timezone.utc) + timedelta(days=365)).replace(minute=0, second=0, microsecond=0)
    end_dt = start_dt + timedelta(minutes=15)
    payload = build_workflow(path, event_id, start_dt.isoformat(), end_dt.isoformat())
    workflow_id = None
    try:
        created = request("POST", f"{base}/api/v1/workflows", key, payload)
        workflow_id = created["id"]
        request("POST", f"{base}/api/v1/workflows/{workflow_id}/activate", key)
        result = call_webhook(f"{base}/webhook/{path}")
        public_result = {key: result.get(key) for key in ("freeBusyOk", "created", "fetched", "deletionConfirmed")}
        print(json.dumps(public_result, indent=2))
        if not all(public_result.values()):
            print(json.dumps({
                "createDiagnostic": result.get("createDiagnostic"),
                "createRaw": result.get("createRaw"),
                "fetchDiagnostic": result.get("fetchDiagnostic"),
            }, indent=2)[:4000])
            raise RuntimeError("calendar smoke test did not satisfy every assertion")
    finally:
        if workflow_id:
            try:
                request("POST", f"{base}/api/v1/workflows/{workflow_id}/deactivate", key)
            finally:
                request("DELETE", f"{base}/api/v1/workflows/{workflow_id}", key)


if __name__ == "__main__":
    main()
