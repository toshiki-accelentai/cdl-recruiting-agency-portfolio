#!/usr/bin/env python3
"""Create or update the legacy monolithic CDL workflow as an inactive draft.

Dry-run by default. This script never activates a workflow.

Use scripts/deploy_n8n_suite.py for the production architecture. Recreating the
retired monolith requires the explicit --legacy-monolith flag.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_PATH = ROOT / "config" / "n8n" / "production" / "cdl-intake-production.json"


def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def request(method: str, url: str, api_key: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "X-N8N-API-KEY": api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            content = response.read()
            return json.loads(content.decode()) if content else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:2000]
        raise RuntimeError(f"{method} {url} -> HTTP {exc.code}: {detail}") from exc


def deployable(workflow: dict) -> dict:
    return {key: workflow[key] for key in ("name", "nodes", "connections", "settings")}


def main() -> None:
    if "--legacy-monolith" not in sys.argv:
        sys.exit("legacy monolith retired; use scripts/deploy_n8n_suite.py")
    apply = "--apply" in sys.argv
    env = load_env()
    base_url = env.get("N8N_BASE_URL", "").rstrip("/")
    api_key = env.get("N8N_API_KEY", "")
    if not base_url or not api_key:
        sys.exit("N8N_BASE_URL / N8N_API_KEY missing from .env")

    workflow = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    payload = deployable(workflow)
    query = urllib.parse.urlencode({"limit": 250})
    listing = request("GET", f"{base_url}/api/v1/workflows?{query}", api_key)
    existing = next((item for item in listing.get("data", []) if item.get("name") == payload["name"]), None)

    action = "update" if existing else "create"
    print(f"workflow: {payload['name']}")
    print(f"action: {action}")
    print(f"nodes: {len(payload['nodes'])}")
    print("activation: never (draft only)")
    if not apply:
        print("dry run; pass --apply to write the inactive draft")
        return

    if existing:
        result = request("PUT", f"{base_url}/api/v1/workflows/{existing['id']}", api_key, payload)
    else:
        result = request("POST", f"{base_url}/api/v1/workflows", api_key, payload)
    print(f"workflow id: {result['id']}")
    print(f"active: {result.get('active', False)}")


if __name__ == "__main__":
    main()
