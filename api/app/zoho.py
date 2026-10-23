"""Zoho Recruit client for the outbox worker.

Every failure is classified so the worker can react correctly:
  kind="retry": Zoho or the network is having trouble; the same request may work later.
  kind="fail":  retrying cannot help (bad data, bad credentials); a human has to look.
An expired access token (401) is handled here: refresh once and retry, invisibly to the worker.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

from app.helpers import parse_experience_years, split_name

ACCOUNTS_DOMAIN = "https://accounts.zoho.com"
RECRUIT_API = "https://recruit.zoho.com/recruit/v2"
TOKEN_SAFETY_MARGIN = 60  # refresh this many seconds before the 1-hour token really expires
RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}
# What real Zoho answers when you update a candidate id that does not exist (probed live 2026-10-13).
MISSING_ID_MESSAGE = "the id given seems to be invalid"

logger = logging.getLogger(__name__)


class ZohoError(Exception):
    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


def urllib_http(method: str, url: str, headers: dict, body: bytes | None, timeout: float):
    """Default transport: (status, parsed JSON or None). Network problems raise OSError."""
    request = urllib.request.Request(url, data=body, method=method,
                                     headers={"User-Agent": "curl/8.0", **headers})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            return response.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            return exc.code, (json.loads(raw) if raw else None)
        except ValueError:
            return exc.code, {"message": raw.decode(errors="replace")[:200]}


def candidate_fields(applicant: dict) -> dict:
    first, last = split_name(applicant["name"])
    fields = {
        "Last_Name": last, "Phone": applicant["phone_e164"], "City": applicant["city"],
        "State": applicant["state"], "Zip_Code": applicant["zip_code"],
        "Source": "Phone Call",
    }
    years = parse_experience_years(applicant["experience"])
    if years is not None:  # unreadable text must not become "0 years" in Zoho
        fields["Experience_in_Years"] = years
    if first:
        fields["First_Name"] = first
    return fields


class ZohoClient:
    def __init__(self, client_id: str, client_secret: str, refresh_token: str, *,
                 accounts_domain: str = ACCOUNTS_DOMAIN, api_base: str = RECRUIT_API,
                 http: Callable = urllib_http, clock: Callable[[], float] = time.monotonic,
                 timeout: float = 15):
        self._creds = (client_id, client_secret, refresh_token)
        self._accounts = accounts_domain.rstrip("/")
        self._api = api_base.rstrip("/")
        self._http, self._clock, self._timeout = http, clock, timeout
        self._token: str | None = None
        self._expires_at = 0.0

    # --- auth -------------------------------------------------------------------------------
    def _access_token(self) -> str:
        if self._token and self._clock() < self._expires_at - TOKEN_SAFETY_MARGIN:
            return self._token
        client_id, client_secret, refresh_token = self._creds
        body = urllib.parse.urlencode({
            "grant_type": "refresh_token", "client_id": client_id,
            "client_secret": client_secret, "refresh_token": refresh_token}).encode()
        status, data = self._send("POST", f"{self._accounts}/oauth/v2/token",
                                  {"Content-Type": "application/x-www-form-urlencoded"}, body)
        data = data or {}
        if status in RETRYABLE_STATUS or status >= 500:
            raise ZohoError("retry", f"token endpoint HTTP {status}")
        if "access_token" not in data:
            raise ZohoError("fail", f"cannot get access token: {data.get('error', f'HTTP {status}')}")
        self._token = data["access_token"]
        self._expires_at = self._clock() + float(data.get("expires_in", 3600))
        return self._token

    # --- transport --------------------------------------------------------------------------
    def _send(self, method, url, headers, body):
        try:
            return self._http(method, url, headers, body, self._timeout)
        except (OSError, TimeoutError) as exc:  # connection refused, DNS, timeout
            raise ZohoError("retry", f"network error: {exc}") from exc

    def _request(self, method: str, path: str, *, params: dict | None = None, payload: dict | None = None):
        url = f"{self._api}{path}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
        body = json.dumps(payload).encode() if payload is not None else None
        for attempt in (1, 2):
            headers = {"Authorization": f"Zoho-oauthtoken {self._access_token()}"}
            if body is not None:
                headers["Content-Type"] = "application/json"
            status, data = self._send(method, url, headers, body)
            if status == 401 and attempt == 1:  # token expired or revoked: mint a new one, retry once
                self._token = None
                continue
            break
        if status == 204:
            return None
        if status in RETRYABLE_STATUS or status >= 500:
            raise ZohoError("retry", f"Zoho HTTP {status}: {(data or {}).get('message', '')}")
        if status >= 400:
            raise ZohoError("fail", f"Zoho HTTP {status}: {(data or {}).get('message', data)}")
        record = ((data or {}).get("data") or [None])[0] if isinstance(data, dict) else None
        if isinstance(record, dict) and record.get("code") not in (None, "SUCCESS"):
            raise ZohoError("fail", f"Zoho {record.get('code')}: {record.get('message', '')}")
        return data

    # --- operations -------------------------------------------------------------------------
    def find_candidate_id(self, phone_e164: str) -> str | None:
        # NOT the phone= parameter: it never matched an existing candidate (verified against live Zoho).
        data = self._request("GET", "/Candidates/search",
                             params={"criteria": f"(Phone:equals:{phone_e164})", "per_page": 1})
        rows = (data or {}).get("data") or []
        return rows[0]["id"] if rows else None

    def upsert_candidate(self, phone_e164: str, fields: dict, known_id: str | None = None) -> str:
        """Update the candidate we already stored the id of, else find by phone, else create.

        known_id wins over the phone search: after a recruiter corrects the phone, the new number
        matches nothing in Zoho and a search would create a duplicate candidate.
        """
        payload = {"data": [fields], "trigger": []}
        if known_id:
            try:
                self._request("PUT", f"/Candidates/{known_id}", payload=payload)
                return known_id
            except ZohoError as exc:
                # Only "that record is gone" (someone deleted it in Zoho) may fall back. Any other
                # failure, including other INVALID_DATA such as a bad ZIP, must surface unchanged.
                if exc.kind != "fail" or MISSING_ID_MESSAGE not in str(exc):
                    raise
                logger.warning("stored Zoho candidate id no longer exists; searching by phone instead")
        existing = self.find_candidate_id(phone_e164)
        if existing:
            self._request("PUT", f"/Candidates/{existing}", payload=payload)
            return existing
        data = self._request("POST", "/Candidates", payload=payload)
        return data["data"][0]["details"]["id"]

    def add_note(self, candidate_id: str, title: str, content: str) -> None:
        self._request("POST", "/Notes", payload={"data": [{
            "Note_Title": title, "Note_Content": content,
            "Parent_Id": candidate_id, "se_module": "Candidates"}]})
