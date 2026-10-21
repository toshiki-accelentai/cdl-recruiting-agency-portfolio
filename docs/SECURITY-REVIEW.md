# Security review (C3 step 6), first pass

Date: 2026-10-20. Scope: backend code in `api/app/`, `api/deploy/compose.yaml`, `api/Dockerfile`, migrations.
Method: one reader (Claude) going through the code. This is NOT the independent review: no second agent,
no human, no live probing, no Caddy config read. The UI files were skipped (being changed in another tool).
Nothing live was touched.

## Ranked findings

| # | Severity | Finding | Where | Fix |
|---|---|---|---|---|
| 1 | HIGH (before the link is shared) | A `recruiter` login can write to the owner's real Zoho: `PATCH /api/calls/{id}` inserts an outbox row and the worker sends a note | `corrections.py` `_correct_existing`, `_attach_applicant` | C4 step 1: `is_demo` rows create no outbox row. Until then, do not hand out the demo password |
| 2 | HIGH (same cause) | The demo user can read real callers: names, phones, summaries, transcripts and recordings through `/api/calls`, `/api/todo`, `/api/applicants/{id}`, `/api/calls/{id}/recording` | `dashboard.py`, `todo.py`, `applicants.py`, `call_reports.py` | Scope EVERY read by role (`is_demo`), including the recording and history endpoints. Test: demo user gets 404 for a real call id on each endpoint |
| 3 | MEDIUM | `last_error` from the worker is returned to every logged-in user; it may contain Zoho error text or internal detail | `dashboard.py` `to_item`, `worker.py:125` | Return the error only to `admin`; demo sees "failed" and the attempt count |
| 4 | MEDIUM | `zoho_candidate_id` is returned to every role | `dashboard.py`, `todo.py`, `applicants.py` | Planned owner-only `zoho_url`; drop the raw id for non-admin |
| 5 | MEDIUM | No rate limit on authenticated writes or reads; a logged-in visitor can write unlimited audit rows and notes | `corrections.py`, `follow_up.py` | C4 rate limit (per user), plus the nightly reset |
| 6 | MEDIUM | Login throttle is in memory: a container restart clears it, and it is per process | `throttle.py` | Acceptable for one process. Say so in the write-up; optional DB-backed counter |
| 7 | LOW | The throttle trusts the first `X-Forwarded-For` entry. Safe only if Caddy overwrites the header (default for an untrusted client) and nothing else can reach `cdl-api:8000`. Any container on `n8n_app` (n8n itself) can reach it and spoof the header | `throttle.py` `client_ip`, `compose.yaml` | Confirm Caddy config has no `trusted_proxies`; accept the n8n-network risk or use a separate network for Caddy |
| 8 | LOW | The session cookie is stateless: logout only deletes it in the browser; a stolen cookie works until it expires (8 h) or the password changes | `auth.py` `logout` | Accept, or bump `session_version` on logout (logs out every device, so not recommended for a shared demo user) |
| 9 | LOW | The container runs as root | `Dockerfile` | Add `USER` with a non-root user |
| 10 | LOW | No request body size limit in the app (`/call-reports` takes arbitrary `artifact` / `messages` JSON; only n8n can reach it) | `call_reports.py` | Limit at Caddy for the public host; n8n-only paths are low risk |
| 11 | INFO | Security headers (CSP, `X-Frame-Options`, `nosniff`, HSTS) are not set in the app. Not checked in Caddy | `pages.py` | Check the live response headers; add in Caddy if missing |
| 12 | INFO | HTTP/3 vs UDP 443 mismatch noted in the C4 plan | Caddy / VPS firewall | Verify from outside; unrelated to the code |

## Checked and fine

- SQL: every query is parameterised. The two f-string SQL spots (`corrections.py`, `follow_up.py`) take column names from fixed maps, never from the request. `dashboard.py` sort is a fixed dict.
- Passwords: argon2; unknown user costs the same as a wrong password (`DUMMY_HASH`); the throttle runs before hashing; the log never holds the username or password.
- Cookie: signed, `HttpOnly`, `SameSite=Lax`, `Secure` on by default, 8 h expiry, `session_version` revokes all on a password change.
- CSRF: writes are JSON `PATCH` with a `Lax` cookie; a cross-site page cannot send the cookie on that request. Login CSRF is low impact.
- Inputs: `extra="forbid"` on corrections and follow-up, length limits, a fixed set for status and temperature.
- n8n endpoints: `hmac.compare_digest`, 503 when the key is unset, 404 for anything that came through the proxy.
- `/docs`, `/redoc`, `/openapi.json` are off.
- Recording: the call id is regex-checked before it goes into a URL, no redirect is followed, only `https://` Location is accepted, the response is `no-store`, the VAPI key never reaches the browser.
- RLS is enabled on every table (006, 007, 008; 009–012 add no tables).
- No `innerHTML` / `insertAdjacentHTML` / `document.write` in the current `static/*.js` (stored notes are rendered as text). Re-check after the UI rewrite.
- Compose: no published ports; the API container gets only `DATABASE_URL` and `.env.api`; the worker does not see the shared secret.

## Not reviewed (needs a second pair of eyes)

- Caddy config and live response headers; DNS; VPS firewall.
- `.env` file permissions on the server; whether the Supabase DB password has ever been in a log.
- The n8n workflows that call the API.
- The new UI code (in progress elsewhere).

## Next

1. Findings 1–4 are fixed by C4 step 1 (test first). Add one test per read endpoint for finding 2.
2. Run the independent pass (two reviewer agents, plus a human if the mentor agrees) against this list.
3. Do not share the demo password until findings 1–2 are fixed and deployed.
