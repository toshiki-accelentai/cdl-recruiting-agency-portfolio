#!/usr/bin/env python3
"""Push ONLY the system prompt text of the live VAPI assistants from config/vapi/prompts/.

deploy_vapi.py also manages the model and temperature, and desired.json has drifted from live
(live runs gpt-5; desired.json says gpt-4.1 / 0.3), so applying it would silently change the
model. This script sends back the live `model` object with just the system message replaced.
Dry-run by default; --apply patches. Optional: --only new-lead | existing-lead.

Going live: the owner reports that VAPI publishes a change made through the API by itself, with no
Publish click, and this was checked on 2026-10-27: after a PATCH (Existing Lead v18) a simulation on the live
assistant ran the new prompt. (A note from 2026-10-09 said a click was needed; that no longer holds.)
Do NOT press Publish on an old dashboard draft afterwards: GET /assistant/{id}/draft can still hold a stale
draft (Existing Lead has one from 2026-08-12), and publishing it would overwrite this script's change.
"""
from __future__ import annotations

import difflib
import json
import sys
from pathlib import Path

try:
    from .deploy_vapi import API, VAPI_DIR, load_env, request
except ImportError:
    from deploy_vapi import API, VAPI_DIR, load_env, request


def main() -> None:
    apply = "--apply" in sys.argv
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    key = load_env().get("VAPI_PRIVATE_KEY") or sys.exit("VAPI_PRIVATE_KEY missing from .env")
    cfg = json.loads((VAPI_DIR / "desired.json").read_text(encoding="utf-8"))

    for slug, spec in cfg["assistants"].items():
        if only and slug != only:
            continue
        live = request("GET", f"{API}/assistant/{spec['id']}", key)
        prompt = (VAPI_DIR / spec["promptFile"]).read_text(encoding="utf-8").strip()
        model = json.loads(json.dumps(live["model"]))  # deep copy of the live model object
        system = [m for m in model["messages"] if m.get("role") == "system"]
        if len(system) != 1:
            sys.exit(f"{slug}: expected exactly one system message, found {len(system)}")
        old = system[0]["content"]
        print(f"\n=== {slug} ({spec['id']}) model={model.get('model')} ===")
        if old.strip() == prompt:
            print("  prompt already matches; nothing to do")
            continue
        system[0]["content"] = prompt
        for line in difflib.unified_diff(old.splitlines(), prompt.splitlines(), "live", "file", lineterm="", n=0):
            print("  " + line[:200])
        if apply:
            result = request("PATCH", f"{API}/assistant/{spec['id']}", key, {"model": model})
            after = [m for m in result["model"]["messages"] if m.get("role") == "system"]
            ok = len(after) == 1 and after[0]["content"].strip() == prompt
            same_model = result["model"].get("model") == live["model"].get("model")
            print(f"  -> APPLIED; prompt matches={ok}; model unchanged={same_model}")
            if not (ok and same_model):
                sys.exit("verification failed, check the assistant in VAPI")
    if not apply:
        print("\nDry run; nothing was modified. Re-run with --apply to deploy.")


if __name__ == "__main__":
    main()
