#!/usr/bin/env python3
"""B1 follow-up: the LIVE Applicant Intake books and says 'saved' only if the database save worked.

Adds two nodes ('Saved to Database?' and 'Respond Save Failure') to the live, hand-edited Intake
and rewires one edge (see require_database_save). Run deploy_intake_database_first.py first.
Dry-run by default; never activates anything.
"""
from __future__ import annotations

import json
import sys
import urllib.parse

try:
    from .build_modular_workflows import require_database_save
    from .deploy_n8n_workflow import deployable, load_env, request
except ImportError:
    from build_modular_workflows import require_database_save
    from deploy_n8n_workflow import deployable, load_env, request

INTAKE_NAME = "CDL 02 - Applicant Intake"
EXPECTED_ADDED = {"Saved to Database?", "Respond Save Failure"}
KEPT_SETTINGS = {"executionOrder", "timezone", "saveDataErrorExecution", "saveDataSuccessExecution",
                 "saveManualExecutions", "saveExecutionProgress", "errorWorkflow", "executionTimeout",
                 "callerPolicy"}


def main() -> None:
    apply = "--apply" in sys.argv
    env = load_env()
    base = env["N8N_BASE_URL"].rstrip("/")
    api_key = env["N8N_API_KEY"]
    listing = request("GET", f"{base}/api/v1/workflows?{urllib.parse.urlencode({'limit': 250})}", api_key)
    live = next(w for w in listing["data"] if w["name"] == INTAKE_NAME)
    patched = require_database_save(live)

    old = {n["name"]: n for n in live["nodes"]}
    added = sorted(n["name"] for n in patched["nodes"] if n["name"] not in old)
    changed = sorted(n["name"] for n in patched["nodes"] if n["name"] in old and n != old[n["name"]])
    print(f"{INTAKE_NAME} (id {live['id']}, active={live['active']})")
    print(f"nodes: {len(live['nodes'])} -> {len(patched['nodes'])}; added: {added}; changed: {changed}")
    print("Intake Valid? true ->", [e["node"] for e in patched["connections"]["Intake Valid?"]["main"][0]])
    if live["active"]:
        sys.exit("refusing: workflow is ACTIVE; deactivate first (default-inactive rule)")
    if not added and not changed:
        print("already patched; nothing to do")
        return
    if set(added) != EXPECTED_ADDED or changed or "Prepare Booking Input" not in old:
        sys.exit("unexpected diff, refusing (is deploy_intake_database_first.py applied?)")
    if not apply:
        print("dry run; pass --apply to write")
        return

    payload = deployable(patched)
    payload["settings"] = {k: v for k, v in live["settings"].items() if k in KEPT_SETTINGS}
    result = request("PUT", f"{base}/api/v1/workflows/{live['id']}", api_key, payload)
    print(json.dumps({"id": result["id"], "active": result.get("active"), "nodes": len(result["nodes"])}))
    if result.get("active"):
        raise RuntimeError("workflow unexpectedly active")


if __name__ == "__main__":
    main()
