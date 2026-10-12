"""Runs INSIDE the cdl-api container (piped to `python -` over ssh) to prove the API key check works.

Sends three POSTs with an empty body: none of them can save anything (a 422 means the key was
accepted but the body was invalid). Prints status codes only, never the secret.
"""
import os
import urllib.error
import urllib.request

URL = "http://localhost:8000/calls"


def post(key):
    headers = {"Content-Type": "application/json"}
    if key is not None:
        headers["X-API-Key"] = key
    req = urllib.request.Request(URL, data=b"{}", method="POST", headers=headers)
    try:
        return urllib.request.urlopen(req, timeout=5).status
    except urllib.error.HTTPError as exc:
        return exc.code


secret = os.environ.get("API_SHARED_SECRET", "")
print(f"secret configured in the container: {bool(secret)} (length {len(secret)})")
print(f"no key         -> {post(None)}   (want 401)")
print(f"wrong key      -> {post('wrong-key')}   (want 401)")
print(f"right key, {{}}  -> {post(secret)}   (want 422: key accepted, body invalid, nothing saved)")
