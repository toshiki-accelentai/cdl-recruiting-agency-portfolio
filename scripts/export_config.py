#!/usr/bin/env python3
"""Export live VAPI + n8n config into version-controlled JSON, with secrets redacted.

Reads credentials from .env (never printed). Writes to config/vapi/ and config/n8n/.

Usage:  python scripts/export_config.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_VAPI = ROOT / "config" / "vapi"
OUT_N8N = ROOT / "config" / "n8n"

# Workflows that make up the CDL system. Everything else in the n8n account is
# unrelated client work and is deliberately not exported.
CDL_WORKFLOWS = {
    "uT4iroyZm4hr2zay": "cdl-recruiting-agency--LIVE",
    "cES82YLOhxJ3EKkK": "cdl-main--zoho-variant",
    "tf3wQ3Sf9c5yfaYB": "cdl-recruiting-agency--zoho-integration",
    "UAtyhlBIztuIrTQ9": "cdl-database-checker",
    "piFq0YIwpSORj9Qs": "cdl-post-call-analysis",
    "k6b44U00Y1AhXJuP": "zoho-integration",
}

CDL_ASSISTANTS = {
    "6901a714-a6c5-45a2-9395-455e09e0051b": "new-lead",
    "542bae1c-51b5-4d83-a3fe-446836b4801d": "existing-lead",
}

CDL_TOOLS = {"41a0ca37-e396-4aac-bd6c-472a33a45ef1": "logApplicantInfo"}

# Keys whose values are secrets wherever they appear.
SECRET_KEYS = {"client_secret", "refresh_token", "client_id", "access_token",
               "api_key", "apikey", "authorization", "password", "token"}

# Zoho tokens/ids look like 1000.<hex>.<hex> or 1000.<alnum>
ZOHO_TOKEN_RE = re.compile(r"\b1000\.[A-Za-z0-9]{10,}(?:\.[A-Za-z0-9]{10,})*\b")
# Generic long hex secrets (Zoho client_secret is 40+ hex chars)
LONG_HEX_RE = re.compile(r"\b[0-9a-f]{32,}\b")

REDACTED = "<<REDACTED:set-via-n8n-credential>>"


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    path = ROOT / ".env"
    if not path.exists():
        sys.exit(".env not found")
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def redact(node):
    """Recursively strip secrets from an exported config tree."""
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            # n8n stores http node body params as {"name": "client_secret", "value": "..."}
            if k == "value" and str(node.get("name", "")).lower() in SECRET_KEYS:
                out[k] = REDACTED
            elif str(k).lower() in SECRET_KEYS and isinstance(v, str):
                out[k] = REDACTED
            else:
                out[k] = redact(v)
        return out
    if isinstance(node, list):
        return [redact(v) for v in node]
    if isinstance(node, str):
        s = ZOHO_TOKEN_RE.sub(REDACTED, node)
        s = LONG_HEX_RE.sub(REDACTED, s)
        return s
    return node


def get(url: str, headers: dict[str, str]):
    # VAPI sits behind a WAF that rejects the default urllib User-Agent with 403.
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0", **headers})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"  wrote {path.relative_to(ROOT)}")


def main() -> None:
    env = load_env()

    vapi_key = env.get("VAPI_PRIVATE_KEY")
    if not vapi_key:
        sys.exit("VAPI_PRIVATE_KEY missing from .env")
    vh = {"Authorization": f"Bearer {vapi_key}"}

    print("VAPI:")
    for aid, slug in CDL_ASSISTANTS.items():
        write(OUT_VAPI / f"assistant.{slug}.json",
              redact(get(f"https://api.vapi.ai/assistant/{aid}", vh)))
    for tid, slug in CDL_TOOLS.items():
        write(OUT_VAPI / f"tool.{slug}.json",
              redact(get(f"https://api.vapi.ai/tool/{tid}", vh)))

    n8n_base = (env.get("N8N_BASE_URL") or "").rstrip("/")
    n8n_key = env.get("N8N_API_KEY")
    if not (n8n_base and n8n_key):
        sys.exit("N8N_BASE_URL / N8N_API_KEY missing from .env")
    nh = {"X-N8N-API-KEY": n8n_key, "accept": "application/json"}

    print("n8n:")
    for wid, slug in CDL_WORKFLOWS.items():
        wf = get(f"{n8n_base}/api/v1/workflows/{wid}", nh)
        # Drop volatile metadata so diffs show real changes only.
        for noise in ("createdAt", "updatedAt", "versionId", "triggerCount", "shared", "pinData"):
            wf.pop(noise, None)
        write(OUT_N8N / f"{slug}.json", redact(wf))

    print("\nDone. Secrets replaced with", REDACTED)


if __name__ == "__main__":
    main()
