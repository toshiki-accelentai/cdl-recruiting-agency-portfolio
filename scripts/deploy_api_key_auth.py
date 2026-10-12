#!/usr/bin/env python3
"""B3 step 4: make n8n send the API's shared secret (X-API-Key) from a Header Auth credential.

Two steps, each a dry run unless --apply is given:

  py -3.11 scripts/deploy_api_key_auth.py create-credential [--apply]
      Creates the n8n credential "CDL API key" (Header Auth, header X-API-Key) from
      API_SHARED_SECRET in api/deploy/.env.api. Prints the credential id, never the secret.
      The n8n public API cannot list credentials, so run this ONCE and keep the printed id.

  py -3.11 scripts/deploy_api_key_auth.py patch-workflow --credential-id ID [--apply]
      Points the live Intake node 'Save to Database API' at that credential (see
      add_api_key_auth). Only that node changes. The live Intake is ACTIVE on purpose (demo), so
      this updates an active workflow; the script checks it is still active afterwards.

Order matters: do this BEFORE the API starts requiring the key, so there is no window in which
calls are rejected. The old API simply ignores the extra header.
"""
from __future__ import annotations

import json
import sys
import urllib.parse
from pathlib import Path

try:
    from .build_modular_workflows import add_api_key_auth
    from .deploy_n8n_workflow import deployable, load_env, request
except ImportError:
    from build_modular_workflows import add_api_key_auth
    from deploy_n8n_workflow import deployable, load_env, request

ROOT = Path(__file__).resolve().parent.parent
SECRET_FILE = ROOT / "api" / "deploy" / ".env.api"
INTAKE_NAME = "CDL 02 - Applicant Intake"
CREDENTIAL_NAME = "CDL API key"
HEADER_NAME = "X-API-Key"
KEPT_SETTINGS = {"executionOrder", "timezone", "saveDataErrorExecution", "saveDataSuccessExecution",
                 "saveManualExecutions", "saveExecutionProgress", "errorWorkflow", "executionTimeout",
                 "callerPolicy"}


def read_secret() -> str:
    raw = SECRET_FILE.read_text(encoding="utf-8-sig").strip()
    if not raw.startswith("API_SHARED_SECRET="):
        sys.exit(f"{SECRET_FILE} must start with API_SHARED_SECRET=")
    secret = raw.split("=", 1)[1].strip().strip('"').strip("'")
    if len(secret) < 32:
        sys.exit("API_SHARED_SECRET is too short (need at least 32 characters)")
    return secret


def create_credential(apply: bool) -> None:
    env = load_env()
    base = env["N8N_BASE_URL"].rstrip("/")
    secret = read_secret()  # validated even on a dry run
    print(f"n8n host: {urllib.parse.urlparse(base).netloc}")
    print(f"would create credential '{CREDENTIAL_NAME}' (httpHeaderAuth, header {HEADER_NAME}, "
          f"secret length {len(secret)})")
    if not apply:
        print("dry run; pass --apply to create it")
        return
    body = {"name": CREDENTIAL_NAME, "type": "httpHeaderAuth",
            "data": {"name": HEADER_NAME, "value": secret}}
    result = request("POST", f"{base}/api/v1/credentials", env["N8N_API_KEY"], body)
    print(json.dumps({"id": result["id"], "name": result["name"], "type": result["type"]}))


def patch_workflow(credential_id: str, apply: bool) -> None:
    env = load_env()
    base = env["N8N_BASE_URL"].rstrip("/")
    api_key = env["N8N_API_KEY"]
    listing = request("GET", f"{base}/api/v1/workflows?{urllib.parse.urlencode({'limit': 250})}", api_key)
    live = next(w for w in listing["data"] if w["name"] == INTAKE_NAME)
    patched = add_api_key_auth(live, credential_id, CREDENTIAL_NAME)

    old = {n["name"]: n for n in live["nodes"]}
    changed = sorted(n["name"] for n in patched["nodes"] if n != old[n["name"]])
    print(f"{INTAKE_NAME} (id {live['id']}, active={live['active']}, nodes={len(live['nodes'])})")
    print(f"nodes that would change: {changed}")
    if changed not in ([], ["Save to Database API"]):
        sys.exit("unexpected diff, refusing")
    if not changed:
        print("already patched; nothing to do")
        return
    if not apply:
        print("dry run; pass --apply to write")
        return

    payload = deployable(patched)
    payload["settings"] = {k: v for k, v in live["settings"].items() if k in KEPT_SETTINGS}
    result = request("PUT", f"{base}/api/v1/workflows/{live['id']}", api_key, payload)
    check = request("GET", f"{base}/api/v1/workflows/{live['id']}", api_key)
    node = next(n for n in check["nodes"] if n["name"] == "Save to Database API")
    print(json.dumps({"id": result["id"], "active_before": live["active"], "active_after": check["active"],
                      "nodes": len(check["nodes"]), "credentials": node.get("credentials")}))
    if check["active"] != live["active"]:
        raise RuntimeError("workflow active state changed: check the n8n editor now")


def main() -> None:
    args = sys.argv[1:]
    apply = "--apply" in args
    if args[:1] == ["create-credential"]:
        create_credential(apply)
    elif args[:1] == ["patch-workflow"] and "--credential-id" in args:
        patch_workflow(args[args.index("--credential-id") + 1], apply)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
