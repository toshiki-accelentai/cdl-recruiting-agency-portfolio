"""Runs INSIDE the cdl-api container. Only reads and rejected requests; nothing is written to the database.

The throttle check uses a throwaway username and a fake client address, so it cannot lock a real account.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://localhost:8000"
KEY = os.environ.get("API_SHARED_SECRET", "")


def call(method, path, headers=None, body=None, form=None):
    headers = dict(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    try:
        response = urllib.request.urlopen(request, timeout=10)
        return response.status, response.headers
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers


PROXY = {"X-Forwarded-For": "198.51.100.9"}
checks = [
    ("GET /docs", call("GET", "/docs")[0], 404),
    ("GET /redoc", call("GET", "/redoc")[0], 404),
    ("GET /openapi.json", call("GET", "/openapi.json")[0], 404),
    ("GET /docs/oauth2-redirect", call("GET", "/docs/oauth2-redirect")[0], 404),
    ("GET /healthz", call("GET", "/healthz")[0], 200),
    ("POST /calls inside, no key", call("POST", "/calls", body={})[0], 401),
    ("POST /calls inside, wrong key", call("POST", "/calls", {"X-API-Key": "wrong"}, {})[0], 401),
    ("POST /calls inside, right key, empty body (rejected, nothing saved)", call("POST", "/calls", {"X-API-Key": KEY}, {})[0], 422),
    ("POST /calls via proxy header, right key", call("POST", "/calls", {**PROXY, "X-API-Key": KEY}, {})[0], 404),
    ("POST /calls via proxy header, no key (same 404, no hint)", call("POST", "/calls", PROXY, {})[0], 404),
    ("POST /call-reports inside, right key, empty body (rejected)", call("POST", "/call-reports", {"X-API-Key": KEY}, {})[0], 422),
    ("POST /call-reports via X-Forwarded-Proto, right key", call("POST", "/call-reports", {"X-Forwarded-Proto": "https", "X-API-Key": KEY}, {})[0], 404),
    ("POST /call-reports via Forwarded header, right key", call("POST", "/call-reports", {"Forwarded": "for=198.51.100.9", "X-API-Key": KEY}, {})[0], 404),
    ("GET /login page via proxy header", call("GET", "/login", PROXY)[0], 200),
    ("GET /api/todo, not logged in", call("GET", "/api/todo")[0], 401),
    ("GET /static/app.css", call("GET", "/static/app.css")[0], 200),
]

# login limit: throwaway name, fake address (what Caddy would send), so no real account is touched
throwaway = {"X-Forwarded-For": "198.51.100.77"}
attempts = [call("POST", "/login", throwaway, form={"username": "zz-throwaway", "password": f"wrong-{i}"}) for i in range(6)]
codes = [status for status, _ in attempts]
retry_after = attempts[-1][1].get("Retry-After")
checks.append(("login limit: 5 wrong tries answer 401, the 6th answers 429", codes, [401] * 5 + [429]))
checks.append(("login limit: the 429 carries a Retry-After", bool(retry_after) and int(retry_after) > 0, True))
other = call("POST", "/login", {"X-Forwarded-For": "198.51.100.78"}, form={"username": "zz-throwaway", "password": "wrong"})[0]
checks.append(("login limit: a different address is not blocked (401, not 429)", other, 401))

failed = 0
for name, got, expected in checks:
    ok = got == expected
    failed += not ok
    print(("PASS " if ok else "FAIL ") + f"{name}: got {got}, expected {expected}")
print("all checks passed" if not failed else f"{failed} CHECK(S) FAILED")
