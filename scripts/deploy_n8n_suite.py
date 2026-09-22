#!/usr/bin/env python3
"""Create/update the modular CDL workflow suite as inactive n8n drafts.

Dry-run by default. This deployer never activates workflows.
"""
from __future__ import annotations

import copy
import json
import sys
import urllib.parse
from pathlib import Path

try:
    from .build_modular_workflows import FILES, OUT_DIR, write_suite, build_suite
    from .deploy_n8n_workflow import deployable, load_env, request
except ImportError:
    from build_modular_workflows import FILES, OUT_DIR, write_suite, build_suite
    from deploy_n8n_workflow import deployable, load_env, request


ROOT = Path(__file__).resolve().parent.parent
MANIFEST = OUT_DIR / "deployment-manifest.json"
ORDER = ("booking", "routing", "intake", "post_call")


def inject_booking_id(intake: dict, booking_id: str) -> dict:
    updated = copy.deepcopy(intake)
    execute = next(node for node in updated["nodes"] if node["name"] == "Execute Calendar Booking")
    execute["parameters"]["workflowId"]["value"] = booking_id
    return updated


def upsert(base: str, api_key: str, workflow: dict, existing: dict | None) -> dict:
    payload = deployable(workflow)
    if existing:
        return request("PUT", f"{base}/api/v1/workflows/{existing['id']}", api_key, payload)
    return request("POST", f"{base}/api/v1/workflows", api_key, payload)


def main() -> None:
    apply = "--apply" in sys.argv
    env = load_env()
    base = env["N8N_BASE_URL"].rstrip("/")
    api_key = env["N8N_API_KEY"]
    listing = request(
        "GET",
        f"{base}/api/v1/workflows?{urllib.parse.urlencode({'limit': 250})}",
        api_key,
    )
    by_name = {item["name"]: item for item in listing.get("data", [])}
    suite = build_suite()

    print("modular workflow suite")
    for key in ORDER:
        workflow = suite[key]
        action = "update" if workflow["name"] in by_name else "create"
        print(f"- {workflow['name']}: {action}, {len(workflow['nodes'])} nodes")
    print("activation: never (drafts only)")
    if not apply:
        print("dry run; pass --apply to write the inactive suite")
        return

    deployed: dict[str, dict] = {}
    booking = suite["booking"]
    booking_result = upsert(base, api_key, booking, by_name.get(booking["name"]))
    deployed["booking"] = booking_result

    suite = build_suite(booking_result["id"])
    write_suite(suite)
    for key in ("routing", "intake", "post_call"):
        workflow = suite[key]
        deployed[key] = upsert(base, api_key, workflow, by_name.get(workflow["name"]))

    manifest = {
        key: {
            "id": deployed[key]["id"],
            "name": deployed[key]["name"],
            "active": deployed[key].get("active", False),
            "nodes": len(deployed[key].get("nodes", [])),
        }
        for key in ("routing", "intake", "booking", "post_call")
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    if any(item["active"] for item in manifest.values()):
        raise RuntimeError("a modular draft unexpectedly became active")


if __name__ == "__main__":
    main()
