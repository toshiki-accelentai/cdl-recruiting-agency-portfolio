# Zoho Recruit — credentials and setup

Answers "what keys do I need for Zoho Recruit, and how do I get them".

You already have `ZOHO_CLIENT_ID`, `ZOHO_CLIENT_SECRET` and `ZOHO_REFRESH_TOKEN`
in `.env`. **All three must be rotated** — the same values were hardcoded in the
n8n workflow JSON and are readable by anyone holding the n8n API key
(see `docs/AUDIT.md` #1). The steps below regenerate them.

---

## 1. What Zoho Recruit needs

| Credential | What it is | Where it lives |
|---|---|---|
| `ZOHO_CLIENT_ID` | Consumer key of the connected app | n8n credential store |
| `ZOHO_CLIENT_SECRET` | Consumer secret | n8n credential store |
| `ZOHO_REFRESH_TOKEN` | Long-lived token, exchanged for access tokens | n8n credential store |
| `ZOHO_ACCOUNTS_DOMAIN` | OAuth host for your datacenter | `.env` / workflow config |
| `ZOHO_RECRUIT_API_DOMAIN` | API host for your datacenter | `.env` / workflow config |

There is **no "Zoho Recruit API key"** — it is OAuth 2.0 only. The access token
is short-lived (1 hour) and is derived from the refresh token at runtime; you
never store it.

## 2. Datacenter — confirmed US

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

## 3. Create the connected app (Self Client)

Server-to-server with no user login → **Self Client**, not Web-based.

1. Go to <https://api-console.zoho.com> — signed in as the Recruit admin.
2. **Add Client → Self Client → Create**.
3. Copy the **Client ID** and **Client Secret**.
4. Open the **Generate Code** tab and enter:
   - **Scope:** `ZohoRecruit.modules.ALL,ZohoRecruit.settings.ALL`
   - **Time Duration:** 10 minutes
   - **Scope Description:** anything
5. **Create → pick the correct portal/org → Download/copy the code.**
   This `grant_token` is valid for 10 minutes and is single-use.

`ZohoRecruit.settings.ALL` is needed so we can read module and field metadata to
verify the schema before writing. `modules.ALL` covers Candidates, Notes and
Interviews. Scopes are baked into the refresh token at generation time — adding
a module later means redoing steps 4–6.

## 4. Exchange the code for a refresh token

Within 10 minutes of generating the code. Run from this repo:

```bash
curl -s -X POST "$ZOHO_ACCOUNTS_DOMAIN/oauth/v2/token" \
  -d grant_type=authorization_code \
  -d client_id="$ZOHO_CLIENT_ID" \
  -d client_secret="$ZOHO_CLIENT_SECRET" \
  -d code="<GRANT_TOKEN_FROM_STEP_5>"
```

The response contains `refresh_token` — that is `ZOHO_REFRESH_TOKEN`. It does
not expire, so it only appears in this one response. Save it immediately.

If you get `invalid_code`, the 10 minutes lapsed or the code was already used —
regenerate. If `invalid_client`, the datacenter domain is wrong.

## 5. Store them in n8n, not in the workflow

This is the part that was done wrong. In n8n:

**Credentials → New → Header Auth** is *not* sufficient here because the access
token has to be refreshed. Use one of:

- **Preferred:** n8n **Generic OAuth2 API** credential, with
  `Access Token URL = {ZOHO_ACCOUNTS_DOMAIN}/oauth/v2/token`, grant type
  *Client Credentials*-style refresh, and the client id/secret in the credential
  fields. n8n then handles refresh and caching.
- **Or:** keep the explicit `GET Token` node but move the three values into an
  n8n credential and reference them, so they never appear in the workflow JSON
  or in an export.

Either way the workflow JSON committed to this repo must contain
`<<REDACTED:set-via-n8n-credential>>`, exactly as `config/n8n/*.json` does now.
`scripts/export_config.py` enforces that on every export.

## 6. Verify the token and discover the real schema

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

## 7. Custom fields to create in Zoho Recruit

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

## 8. Rate limits worth knowing

- Access tokens: minting is throttled per refresh token. Cache the token for its
  full hour instead of minting per call (AUDIT #22).
- API credits are per-org per-day and vary by edition; a create + note + update
  per call is 3 credits. Batch where possible.
