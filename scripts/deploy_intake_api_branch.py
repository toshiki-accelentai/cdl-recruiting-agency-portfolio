#!/usr/bin/env python3
"""A3: add the 'Save to Database API' side branch to the LIVE Applicant Intake workflow.

The live Intake was hand-edited in the n8n UI, so this does NOT redeploy the generated
suite (that would overwrite those edits). It reads the live workflow, adds exactly one node
and one edge, and writes it back. Dry-run by default; never activates anything.
"""
from __future__ import annotations

import json
import sys
import urllib.parse

try:
    from .build_modular_workflows import add_save_to_api_branch
    from .deploy_n8n_workflow import deployable, load_env, request
except ImportError:
    from build_modular_workflows import add_save_to_api_branch
    from deploy_n8n_workflow import deployable, load_env, request

INTAKE_NAME = "CDL 02 - Applicant Intake"


def main() -> None:
    apply = "--apply" in sys.argv
    env = load_env()
    base = env["N8N_BASE_URL"].rstrip("/")
    api_key = env["N8N_API_KEY"]
    listing = request("GET", f"{base}/api/v1/workflows?{urllib.parse.urlencode({'limit': 250})}", api_key)
    live = next(w for w in listing["data"] if w["name"] == INTAKE_NAME)
    patched = add_save_to_api_branch(live)

    old = {n["name"]: n for n in live["nodes"]}
    changed = [n["name"] for n in patched["nodes"] if n["name"] in old and n != old[n["name"]]]
    added = [n["name"] for n in patched["nodes"] if n["name"] not in old]
    print(f"{INTAKE_NAME} (id {live['id']}, active={live['active']})")
    print(f"nodes: {len(live['nodes'])} -> {len(patched['nodes'])}; added: {added}; other nodes changed: {changed}")
    print("webhook edges:", [e["node"] for e in patched["connections"]["Applicant Intake Webhook"]["main"][0]])
    if live["active"]:
        sys.exit("refusing: workflow is ACTIVE; deactivate first (default-inactive rule)")
    if added != ["Save to Database API"] and not (not added and not changed):
        sys.exit(f"unexpected diff, refusing: added={added}")
    if changed:
        sys.exit(f"unexpected diff, refusing: changed={changed}")
    if not added:
        print("already patched; nothing to do")
        return
    if not apply:
        print("dry run; pass --apply to write")
        return

    payload = deployable(patched)
    payload["settings"] = {k: v for k, v in live["settings"].items() if k in {
        "executionOrder", "timezone", "saveDataErrorExecution", "saveDataSuccessExecution",
        "saveManualExecutions", "saveExecutionProgress", "errorWorkflow", "executionTimeout",
        "callerPolicy"}}
    result = request("PUT", f"{base}/api/v1/workflows/{live['id']}", api_key, payload)
    print(json.dumps({"id": result["id"], "active": result.get("active"), "nodes": len(result["nodes"])}))
    if result.get("active"):
        raise RuntimeError("workflow unexpectedly active")


if __name__ == "__main__":
    main()
