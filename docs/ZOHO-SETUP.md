# Zoho Recruit — credentials and setup

Answers "what keys do I need for Zoho Recruit, and how do I get them".

**Two routes.** Route A (§4A) lets n8n own the OAuth flow and is what we are
doing. Route B (§4B) is the manual Self Client flow, kept as a fallback for
scripts outside n8n.

---

## 1. What is actually wrong today — and what is not

The current workflows do **transport** correctly:

- `Create Candidate` / `Add Note` send `Authorization: Zoho-oauthtoken <token>`
  as a **header**. Correct. Tokens in query strings leak into access logs,
  browser history and `Referer` headers; headers do not.
- `GET Token` sends the client credentials in a **form-urlencoded body** to the
  token endpoint. Also correct — that is what the OAuth 2.0 spec requires.

The problem is **storage at rest**, not transport. `client_id`, `client_secret`
and `refresh_token` are literal strings inside the workflow definition:

```
GET Token → bodyParameters:
   {name: "client_secret", value: "<plaintext>"}
   {name: "refresh_token", value: "<plaintext>"}
```

Which means they are readable with nothing but the n8n API key, present in every
workflow export and backup, visible to anyone with n8n editor access, and
duplicated across three workflows.

Severity comes from the refresh token specifically: the **access token expires
in 1 hour, the refresh token never expires**. Whoever holds it has indefinite
read/write access to the candidate database — real names, phone numbers, work
history — until it is explicitly revoked. Rotating *is* the revocation.

## 2. What Zoho Recruit needs

| Credential | What it is | Where it belongs |
|---|---|---|
| Client ID | Consumer key of the connected app | n8n credential store |
| Client Secret | Consumer secret | n8n credential store |
| Refresh token | Long-lived, exchanged for access tokens | n8n credential store — **or not stored by you at all, see §4A** |
| `ZOHO_ACCOUNTS_DOMAIN` | OAuth host for your datacenter | `.env` |
| `ZOHO_RECRUIT_API_DOMAIN` | API host for your datacenter | `.env` |

There is **no "Zoho Recruit API key"** — it is OAuth 2.0 only. The access token
is short-lived (1 hour) and derived from the refresh token at runtime; it is
never stored.

## 3. Datacenter — confirmed US

The org is at `https://recruit.zoho.com/recruit`, so this is the **US**
datacenter and the domains hardcoded in the existing workflows are correct:

```
ZOHO_ACCOUNTS_DOMAIN=https://accounts.zoho.com
ZOHO_RECRUIT_API_DOMAIN=https://recruit.zoho.com
```

The API Console is correspondingly `https://api-console.zoho.com` (it is
per-datacenter too — an app created in the wrong console cannot authorise
against this org).

Other datacenters, for reference only. A mismatch fails with a bare
`invalid_client` and no useful detail:

| DC | Accounts | API | Console |
|---|---|---|---|
| **US** | **`accounts.zoho.com`** | **`recruit.zoho.com`** | **`api-console.zoho.com`** |
| EU | `accounts.zoho.eu` | `recruit.zoho.eu` | `api-console.zoho.eu` |
| IN | `accounts.zoho.in` | `recruit.zoho.in` | `api-console.zoho.in` |
| AU | `accounts.zoho.com.au` | `recruit.zoho.com.au` | `api-console.zoho.com.au` |

Note this is **Zoho Recruit** (the ATS), not Zoho CRM. Its API lives under the
`/recruit/v2/` path with `ZohoRecruit.*` scopes — CRM's `ZohoCRM.*` scopes and
`/crm/v2/` endpoints will not work against this org, and Recruit's Candidates
module is not CRM's Contacts.

## 4A. Recommended — let n8n own the OAuth flow

This is the best-practice route and the one we are taking. **You never handle a
refresh token at all**: n8n performs the authorisation-code exchange in the
browser, stores the resulting token encrypted in its credential store, and
refreshes it automatically.

Confirmed available on `n8n.accelentai.com`: the generic `oAuth2Api` credential
type exposes `authUrl`, `accessTokenUrl`, `scope` and `authQueryParameters`.
(Do **not** use n8n's built-in `zohoOAuth2Api` — it exposes no `scope` field
because its scopes are hardcoded for Zoho **CRM**, which will not authorise
Recruit.)

**In Zoho API Console** — <https://api-console.zoho.com>, signed in as the
Recruit admin:

1. **Add Client → Server-based Applications** (not Self Client — that type has
   no redirect URI, so n8n cannot complete the flow).
2. **Authorized Redirect URI:** `https://n8n.accelentai.com/rest/oauth2-credential/callback`
   — n8n shows the exact URL on the credential screen; copy it from there rather
   than trusting this line.
3. Copy the **Client ID** and **Client Secret**.

**In n8n** — Credentials → New → **OAuth2 API**:

| Field | Value |
|---|---|
| Grant Type | Authorization Code |
| Authorization URL | `https://accounts.zoho.com/oauth/v2/auth` |
| Access Token URL | `https://accounts.zoho.com/oauth/v2/token` |
| Client ID / Secret | from step 3 |
| Scope | `ZohoRecruit.modules.ALL,ZohoRecruit.settings.ALL` |
| Auth URI Query Parameters | `access_type=offline&prompt=consent` |
| Authentication | Body |

`access_type=offline` is **required** — without it Zoho returns only an access
token and no refresh token, and the credential silently stops working after an
hour. `prompt=consent` forces Zoho to re-issue a refresh token on
re-authorisation instead of returning none.

Then click **Connect my account** and approve.

**What this fixes, beyond the storage problem:**

- Removes the `GET Token` node entirely — no hand-built token exchange.
- Removes the hand-built `Authorization` header, which is where the trailing-space
  bug lives (AUDIT #6). n8n injects the header itself.
- n8n caches and refreshes the access token, fixing the mint-on-every-call
  throttling risk (AUDIT #22).

HTTP Request nodes then set **Authentication → Generic Credential Type → OAuth2
API** and pick this credential. No secret appears anywhere in the workflow JSON.

> Scopes are baked in at authorisation time. Adding a module later means editing
> the scope and clicking **Connect my account** again.
> `ZohoRecruit.settings.ALL` is needed to read module/field metadata (§7);
> `modules.ALL` covers Candidates, Notes and Interviews.

## 4B. Fallback — Self Client (manual)

Only needed for scripts running outside n8n, e.g. the schema discovery in §7
before the n8n credential exists.

1. <https://api-console.zoho.com> → **Add Client → Self Client → Create**.
2. Copy the **Client ID** and **Client Secret**.
3. **Generate Code** tab:
   - **Scope:** `ZohoRecruit.modules.ALL,ZohoRecruit.settings.ALL`
   - **Time Duration:** 10 minutes
4. **Create → pick the correct portal/org → copy the code.** This `grant_token`
   is valid for 10 minutes and is single-use.

If you use this route, the refresh token goes in `.env` only — never in a
workflow node.

## 5. Exchange the code for a refresh token (Route B only)

Within 10 minutes of generating the code. Run from this repo:

```bash
curl -s -X POST "$ZOHO_ACCOUNTS_DOMAIN/oauth/v2/token" \
  -d grant_type=authorization_code \
  -d client_id="$ZOHO_CLIENT_ID" \
  -d client_secret="$ZOHO_CLIENT_SECRET" \
  -d code="<GRANT_TOKEN_FROM_STEP_4>"
```

The response contains `refresh_token` — that is `ZOHO_REFRESH_TOKEN`. It does
not expire, so it only appears in this one response. Save it immediately.

If you get `invalid_code`, the 10 minutes lapsed or the code was already used —
regenerate. If `invalid_client`, the datacenter domain is wrong.

## 6. The rule: no secret in a workflow node

Whichever route you take, the invariant is the same: **no credential value ever
appears in a workflow node's parameters.** Nodes reference a credential by name;
n8n stores the value encrypted and keeps it out of exports.

Concretely, workflow JSON committed to this repo must show
`<<REDACTED:set-via-n8n-credential>>` where a secret used to be — exactly as
`config/n8n/*.json` does now. `scripts/export_config.py` enforces this on every
export, and the check below must return nothing:

```bash
grep -rnE '1000\.[A-Za-z0-9]{10,}|[0-9a-f]{32,}' config/
```

Route A satisfies this by construction, because there is no `GET Token` node
left to put a secret into.

## 7. Verify the token and discover the real schema

Before mapping any fields, confirm what your Recruit edition actually exposes —
module availability differs by edition, and the current workflows assume custom
fields (`Temperature`, `Calendar_URL`, `Status`) that may not exist.

```bash
# 1. mint an access token
ACCESS=$(curl -s -X POST "$ZOHO_ACCOUNTS_DOMAIN/oauth/v2/token" \
  -d grant_type=refresh_token \
  -d client_id="$ZOHO_CLIENT_ID" \
  -d client_secret="$ZOHO_CLIENT_SECRET" \
  -d refresh_token="$ZOHO_REFRESH_TOKEN" | python -c 'import json,sys;print(json.load(sys.stdin)["access_token"])')

# 2. which modules exist?
curl -s "$ZOHO_RECRUIT_API_DOMAIN/recruit/v2/settings/modules" \
  -H "Authorization: Zoho-oauthtoken $ACCESS" | python -m json.tool | grep -E '"api_name"|"module_name"'

# 3. which Candidate fields exist, and which are mandatory?
curl -s "$ZOHO_RECRUIT_API_DOMAIN/recruit/v2/settings/fields?module=Candidates" \
  -H "Authorization: Zoho-oauthtoken $ACCESS" | python -m json.tool | grep -E '"api_name"|"required"'
```

Check specifically for:

- `Interviews` — if present, bookings can live in Zoho instead of only Calendar.
- `Notes` — for call transcripts / call history.
- A `Zip_Code`-style field on Candidates — needed for postcode analysis.
- Whether `Last_Name` and `Email` are mandatory (they usually are). This drives
  the fix for AUDIT #13: the agent currently never collects an email, which is
  why the Zoho upsert cannot deduplicate.

## 8. Custom fields to create in Zoho Recruit

Based on what the workflows try to write, create these on the Candidates module
(Setup → Modules and Fields → Candidates) if they do not already exist:

| Field | Type | Purpose |
|---|---|---|
| `Zip_Code` | Single line | postcode analysis — replaces the Airtable blob |
| `Temperature` | Picklist: HOT / MEDIUM / WARM / COLD | lead urgency |
| `Callback_Time` | Date/Time | confirmed callback slot |
| `Calendar_Event_URL` | URL | link to the Google Calendar event |
| `VAPI_Call_ID` | Single line | idempotency key — dedupe repeat webhooks |

`VAPI_Call_ID` is the one to add even if you skip the rest: it gives the upsert a
stable `duplicate_check_fields` target so a retried webhook updates rather than
duplicates.

## 9. Rate limits worth knowing

- Access tokens: minting is throttled per refresh token. Cache the token for its
  full hour instead of minting per call (AUDIT #22).
- API credits are per-org per-day and vary by edition; a create + note + update
  per call is 3 credits. Batch where possible.
