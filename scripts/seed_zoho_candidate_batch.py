#!/usr/bin/env python3
"""Seed ten synthetic CDL candidates through the real modular intake flow."""
from __future__ import annotations

import json
import sys
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

try:
    from .deploy_n8n_workflow import load_env, request
except ImportError:
    from deploy_n8n_workflow import load_env, request


INTAKE_ID = "CrGEvZ5vuX37rshi"
BOOKING_ID = "nIqItEX8Vbn78sWo"


def saturday_callback() -> str:
    value = datetime.now(ZoneInfo("America/Vancouver")) + timedelta(days=1)
    while value.weekday() != 5:
        value += timedelta(days=1)
    return value.replace(hour=10, minute=0, second=0, microsecond=0).isoformat()


PROFILES = [
    ("Marcus Thompson", "+12025550111", "Tacoma", "WA", "98402", "5+ years", "within 3 days"),
    ("Elena Rodriguez", "+12025550112", "Portland", "OR", "97205", "2 years", "within 7 days"),
    ("Derrick Williams", "+12025550113", "Spokane", "WA", "99201", "1 year", "within 14 days"),
    ("Samantha Nguyen", "+12025550114", "Salem", "OR", "97301", "3+ years", "within 7 days"),
    ("Caleb Anderson", "+12025550115", "Everett", "WA", "98201", "6 months", "within 14 days"),
    ("Jordan Mitchell", "+12025550116", "Vancouver", "WA", "98660", "4 years", "immediately"),
    ("Priya Patel", "+12025550117", "Hillsboro", "OR", "97123", "2+ years", "within 7 days"),
    ("Anthony Brooks", "+12025550118", "Yakima", "WA", "98901", "8 years", "within 3 days"),
    ("Rachel Foster", "+12025550119", "Bend", "OR", "97701", "1+ years", "within 14 days"),
    ("Luis Hernandez", "+12025550120", "Bellingham", "WA", "98225", "3 years", "within 7 days"),
]


def body(index: int, profile: tuple[str, ...], callback: str) -> dict:
    name, phone, city, state, zip_code, experience, readiness = profile
    call_id = f"candidate-batch-20260813-{index:02d}"
    return {"message": {"call": {"id": call_id, "customer": {"number": phone}}, "toolCalls": [{
        "id": f"candidate-batch-tool-{index:02d}", "type": "function", "function": {
            "name": "logApplicantInfo", "arguments": {
                "name": name, "readiness": readiness, "experience": experience,
                "phoneNumber": phone, "city": city, "state": state,
                "zipCode": zip_code, "preferredCallbackTime": callback,
            },
        },
    }]}}


def call(url: str, payload: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as response:
        raw = response.read().decode()
        return json.loads(raw) if raw.strip() else {"emptyResponse": True, "status": response.status}


def main() -> None:
    apply = "--apply" in sys.argv
    callback = saturday_callback()
    print(json.dumps({"count": len(PROFILES), "callback": callback, "profiles": [
        {"name": p[0], "phone": p[1], "city": p[2], "state": p[3], "zipCode": p[4], "experience": p[5], "readiness": p[6]}
        for p in PROFILES
    ]}, indent=2))
    if not apply:
        print("dry run; pass --apply to submit the ten synthetic candidates")
        return

    env = load_env()
    base = env["N8N_BASE_URL"].rstrip("/")
    key = env["N8N_API_KEY"]
    request("POST", f"{base}/api/v1/workflows/{BOOKING_ID}/activate", key)
    request("POST", f"{base}/api/v1/workflows/{INTAKE_ID}/activate", key)
    results = []
    try:
        for index, profile in enumerate(PROFILES, 1):
            result = call(f"{base}/webhook/cdl/log-applicant", body(index, profile, callback))
            results.append({"name": profile[0], "phone": profile[1], "result": result})
        existing = call(f"{base}/webhook/cdl/assistant-request", {"message": {"call": {"id": "candidate-batch-routing-check", "customer": {"number": PROFILES[0][1]}}}})
        print(json.dumps({"intakeResults": results, "existingApplicantRouting": existing}, indent=2))
        if len(results) != 10 or any("results" not in item["result"] for item in results):
            raise RuntimeError("one or more intake responses were malformed")
    finally:
        request("POST", f"{base}/api/v1/workflows/{INTAKE_ID}/deactivate", key)
        request("POST", f"{base}/api/v1/workflows/{BOOKING_ID}/deactivate", key)


if __name__ == "__main__":
    main()
