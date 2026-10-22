"""Asks VAPI for a fresh, short-lived link to a call's recording.

VAPI keeps recordings in a private bucket: the address stored in its call data does not play. With the
private key, GET /call/{id}/mono-recording answers with a redirect to a signed link that expires in 30
minutes. The key stays here, on the server; the browser only ever sees the signed link.
"""
import logging
import os
import re
import urllib.error
import urllib.request
from pathlib import Path

from app.config import vapi_private_key

logger = logging.getLogger(__name__)

VAPI_BASE = "https://api.vapi.ai"
REQUEST_TIMEOUT_SECONDS = 10
PLAIN_CALL_ID = re.compile(r"^[A-Za-z0-9-]{1,64}$")  # the id goes into a URL path: nothing else may through
REDIRECT_CODES = {301, 302, 303, 307, 308}


# The demo server plays two sample recordings from local files instead of asking VAPI. The file name comes from this
# fixed table, keyed by the call's stored id; a request never supplies a name or a path.
DEMO_RECORDING_FILES = {
    "demo-sample-intake": "sample-intake-call.wav",
    "demo-sample-hangup": "sample-incomplete-call.wav",
}


def demo_recordings_dir() -> Path | None:
    """The folder of sample recordings, or None when this is not the demo server."""
    value = os.environ.get("DEMO_RECORDINGS_DIR", "")
    return Path(value) if value else None


def demo_recording_file(folder: Path, vapi_call_id: str) -> Path | None:
    """The sample file for this call, or None when the call has none or the file is not there."""
    name = DEMO_RECORDING_FILES.get(vapi_call_id)
    path = folder / name if name else None
    return path if path is not None and path.is_file() else None


class NotConfigured(Exception):
    """VAPI_PRIVATE_KEY is not set."""


class VapiError(Exception):
    """VAPI could not be asked, or answered something unexpected."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # we want the Location header, not the file
        return None


def _open_without_redirect(url: str, key: str):
    # VAPI's firewall rejects the default Python User-Agent with 403.
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}", "User-Agent": "curl/8.0"})
    return urllib.request.build_opener(_NoRedirect).open(request, timeout=REQUEST_TIMEOUT_SECONDS)


def signed_recording_url(vapi_call_id: str) -> str | None:
    """The signed link, or None when VAPI has no recording for this call."""
    if not PLAIN_CALL_ID.fullmatch(vapi_call_id or ""):
        raise ValueError("not a plain call id")
    key = vapi_private_key()
    if not key:
        raise NotConfigured("VAPI_PRIVATE_KEY is not set")
    try:
        _open_without_redirect(f"{VAPI_BASE}/call/{vapi_call_id}/mono-recording", key)
    except urllib.error.HTTPError as exc:
        if exc.code in REDIRECT_CODES:
            location = exc.headers.get("Location") if exc.headers else None
            if location and location.startswith("https://"):
                return location
            raise VapiError("vapi redirected somewhere unusable")
        if exc.code == 404:
            return None
        raise VapiError(f"vapi answered {exc.code}")
    except (urllib.error.URLError, OSError) as exc:  # never log the URL: it carries a signature
        raise VapiError(f"vapi unreachable: {type(exc).__name__}")
    raise VapiError("vapi did not redirect")
