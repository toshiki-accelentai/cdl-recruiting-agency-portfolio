#!/usr/bin/env python3
"""Apply config/vapi/desired.json to the live VAPI assistants.

Dry-run by default: prints the diff and changes nothing.
Pass --apply to PATCH the live assistants.

    python scripts/deploy_vapi.py            # diff only
    python scripts/deploy_vapi.py --apply    # deploy

Only keys present in desired.json are managed; every other field on the live
assistant is left untouched. `server.url` is preserved from live so this script
can never silently repoint the webhook.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VAPI_DIR = ROOT / "config" / "vapi"
API = "https://api.vapi.ai"


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    path = ROOT / ".env"
    if not path.exists():
        sys.exit(".env not found")
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def request(method: str, url: str, key: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        # VAPI's WAF 403s the default urllib User-Agent.
        headers={
            "User-Agent": "curl/8.0",
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        sys.exit(f"{method} {url} -> HTTP {e.code}\n{e.read().decode()[:2000]}")


def deep_merge(base, overlay):
    """overlay wins, but nested dicts are merged rather than replaced."""
    if not isinstance(base, dict) or not isinstance(overlay, dict):
        return overlay
    out = dict(base)
    for k, v in overlay.items():
        out[k] = deep_merge(base.get(k), v) if k in base else v
    return out


def subset_of(live, desired):
    """Project `live` down to only the keys `desired` declares, for diffing."""
    if not isinstance(desired, dict) or not isinstance(live, dict):
        return live
    return {k: subset_of(live.get(k), v) for k, v in desired.items()}


def summarise(label: str, before, after) -> list[str]:
    """Flatten a nested before/after into readable one-line changes."""
    lines: list[str] = []
    if isinstance(after, dict):
        for k, v in after.items():
            b = before.get(k) if isinstance(before, dict) else None
            lines += summarise(f"{label}.{k}" if label else k, b, v)
        return lines
    if before == after:
        return lines

    def brief(v) -> str:
        """Compact rendering so a 6 KB prompt doesn't flood the diff."""
        if isinstance(v, str) and (len(v) > 70 or "\n" in v):
            return f"<text {len(v)} chars>"
        if isinstance(v, list):
            # Lists of prompt messages are the common case here.
            if v and all(isinstance(i, dict) and "content" in i for i in v):
                return "[" + ", ".join(
                    f"{i.get('role')}:<{len(i.get('content') or '')} chars>" for i in v
                ) + "]"
            return repr(v) if len(repr(v)) <= 70 else f"<list of {len(v)}>"
        if v is None:
            return "unset"
        return repr(v)

    lines.append(f"  ~ {label}: {brief(before)} -> {brief(after)}")
    return lines


def main() -> None:
    apply = "--apply" in sys.argv
    env = load_env()
    key = env.get("VAPI_PRIVATE_KEY")
    if not key:
        sys.exit("VAPI_PRIVATE_KEY missing from .env")

    cfg = json.loads((VAPI_DIR / "desired.json").read_text(encoding="utf-8"))
    shared = cfg["shared"]

    total_changes = 0
    for slug, spec in cfg["assistants"].items():
        aid = spec["id"]
        live = request("GET", f"{API}/assistant/{aid}", key)

        desired = deep_merge(shared, {})
        desired["firstMessage"] = spec["firstMessage"]
        if spec.get("name"):
            desired["name"] = spec["name"]

        prompt = (VAPI_DIR / spec["promptFile"]).read_text(encoding="utf-8").strip()
        desired["model"] = deep_merge(
            desired.get("model", {}),
            {"messages": [{"role": "system", "content": prompt}]},
        )

        # Never let this script move the webhook — carry live's url through.
        live_url = (live.get("server") or {}).get("url")
        if live_url:
            desired["server"] = deep_merge(desired.get("server", {}), {"url": live_url})

        before = subset_of(live, desired)
        changes = summarise("", before, desired)

        print(f"\n=== {slug}  ({aid}) ===")
        if not changes:
            print("  no changes")
            continue
        total_changes += len(changes)
        print("\n".join(changes))

        if apply:
            request("PATCH", f"{API}/assistant/{aid}", key, desired)
            print("  -> APPLIED")

    print()
    if not apply:
        print(f"{total_changes} change(s). Dry run — nothing was modified.")
        print("Re-run with --apply to deploy.")
    else:
        print(f"{total_changes} change(s) applied.")
        print("Re-run `python scripts/export_config.py` to resync config/.")


if __name__ == "__main__":
    main()
