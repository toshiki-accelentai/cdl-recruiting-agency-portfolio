#!/usr/bin/env python3
"""Diff or deploy the versioned VAPI logApplicantInfo tool contract.

Dry-run by default. The live server URL is preserved unless both --apply and
--repoint-server are explicitly passed.
"""
from __future__ import annotations

import copy
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DESIRED_PATH = ROOT / "config" / "vapi" / "tool.logApplicantInfo.desired.json"
API = "https://api.vapi.ai"


def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    path = ROOT / ".env"
    if not path.exists():
        raise RuntimeError(".env not found")
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def request(method: str, url: str, key: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "User-Agent": "curl/8.0",
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:2000]
        raise RuntimeError(f"{method} {url} -> HTTP {exc.code}: {detail}") from exc


def build_payload(live: dict, desired: dict, repoint_server: bool) -> dict:
    payload = copy.deepcopy(desired)
    payload.pop("id", None)
    live_url = (live.get("server") or {}).get("url")
    if not repoint_server and live_url:
        payload.setdefault("server", {})["url"] = live_url
    return payload


def project_live(live, desired):
    if isinstance(desired, dict) and isinstance(live, dict):
        return {key: project_live(live.get(key), value) for key, value in desired.items()}
    return live


def main() -> None:
    apply = "--apply" in sys.argv
    repoint = "--repoint-server" in sys.argv
    if repoint and not apply:
        raise SystemExit("--repoint-server requires --apply")

    env = load_env()
    desired = json.loads(DESIRED_PATH.read_text(encoding="utf-8"))
    key = env.get("VAPI_PRIVATE_KEY", "")
    tool_id = env.get("VAPI_LOG_APPLICANT_TOOL_ID", "") or desired.get("id", "")
    if not key or not tool_id:
        raise SystemExit("VAPI_PRIVATE_KEY / tool id missing")
    live = request("GET", f"{API}/tool/{tool_id}", key)
    payload = build_payload(live, desired, repoint)
    before = project_live(live, payload)

    print(f"tool: {tool_id}")
    print(f"schema changed: {before.get('function') != payload.get('function')}")
    print(f"server URL: {(payload.get('server') or {}).get('url', 'unset')}")
    print(f"server repoint authorized: {repoint}")
    if before == payload:
        print("no changes")
        return
    if not apply:
        print("dry run; pass --apply to update the contract without repointing")
        return

    result = request("PATCH", f"{API}/tool/{tool_id}", key, payload)
    print(f"updated tool: {result.get('id', tool_id)}")


if __name__ == "__main__":
    main()
