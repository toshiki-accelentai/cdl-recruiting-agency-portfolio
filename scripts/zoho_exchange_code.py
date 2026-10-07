#!/usr/bin/env python3
"""Exchange a Zoho Self Client grant code for a refresh token (docs/ZOHO-SETUP.md §5).

Run it yourself in your own terminal: the refresh token is printed to YOUR screen only,
so it never passes through a chat. Reads ZOHO_CLIENT_ID / ZOHO_CLIENT_SECRET (and optionally
ZOHO_ACCOUNTS_DOMAIN) from .env. The grant code is single-use and valid for 10 minutes.

    py -3.11 scripts/zoho_exchange_code.py <GRANT_CODE>
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request

try:
    from .deploy_n8n_workflow import load_env
except ImportError:
    from deploy_n8n_workflow import load_env


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: py -3.11 scripts/zoho_exchange_code.py <GRANT_CODE>")
    env = load_env()
    missing = [k for k in ("ZOHO_CLIENT_ID", "ZOHO_CLIENT_SECRET") if not env.get(k)]
    if missing:
        sys.exit(f"missing in .env: {', '.join(missing)}")
    domain = env.get("ZOHO_ACCOUNTS_DOMAIN", "https://accounts.zoho.com").rstrip("/")
    body = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "client_id": env["ZOHO_CLIENT_ID"],
        "client_secret": env["ZOHO_CLIENT_SECRET"],
        "code": sys.argv[1],
    }).encode()
    request = urllib.request.Request(
        f"{domain}/oauth/v2/token", data=body, method="POST", headers={"User-Agent": "curl/8.0"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        sys.exit(f"HTTP {exc.code}: {exc.read().decode(errors='replace')[:200]}")
    if "refresh_token" not in data:
        sys.exit(f"no refresh_token in response; error={data.get('error')!r} (code expired or already used?)")
    print("Copy this line into .env (replace the old ZOHO_REFRESH_TOKEN line):")
    print(f"ZOHO_REFRESH_TOKEN={data['refresh_token']}")


if __name__ == "__main__":
    main()
