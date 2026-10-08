#!/usr/bin/env python3
"""B1 follow-up: make the outbox worker the only Zoho writer in the LIVE Applicant Intake.

The live Intake was hand-edited in the n8n UI, so this does NOT redeploy the generated suite.
It reads the live workflow, removes the Zoho-writing nodes, repoints the booking path and writes
it back (see make_database_first). Dry-run by default; never activates anything.
"""
from __future__ import annotations

import json
import sys
import urllib.parse

try:
    from .build_modular_workflows import ZOHO_WRITER_NODES, make_database_first
    from .deploy_n8n_workflow import deployable, load_env, request
except ImportError:
    from build_modular_workflows import ZOHO_WRITER_NODES, make_database_first
    from deploy_n8n_workflow import deployable, load_env, request

INTAKE_NAME = "CDL 02 - Applicant Intake"
EXPECTED_CHANGED = {"Prepare Booking Input", "Normalize Booking Outcome"}
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
    patched = make_database_first(live)

    old = {n["name"]: n for n in live["nodes"]}
    removed = sorted(set(old) - {n["name"] for n in patched["nodes"]})
    changed = sorted(n["name"] for n in patched["nodes"] if n != old[n["name"]])
    print(f"{INTAKE_NAME} (id {live['id']}, active={live['active']})")
    print(f"nodes: {len(live['nodes'])} -> {len(patched['nodes'])}")
    print("removed:", removed)
    print("changed:", changed)
    if live["active"]:
        sys.exit("refusing: workflow is ACTIVE; deactivate first (default-inactive rule)")
    if not removed and not changed:
        print("already patched; nothing to do")
        return
    if set(removed) != ZOHO_WRITER_NODES or set(changed) != EXPECTED_CHANGED:
        sys.exit("unexpected diff, refusing (live workflow differs from what the patch expects)")
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
