# cdl-recruiting-agency-portfolio

Voice AI intake for **Frontline CDL Staffing**, a US commercial truck driver
staffing agency. An inbound caller (a CDL driver looking for work) is qualified
by a VAPI voice agent, which logs the applicant and books a recruiter callback.

## Stack

| Layer | Service |
|---|---|
| Voice agent | VAPI (GPT-4.1, Deepgram nova-3, VAPI "Harry" voice) |
| Orchestration | n8n |
| ATS / system of record | Zoho Recruit *(target — not yet wired, see AUDIT #3)* |
| Calendar | Google Calendar (`toshiki@accelentai.com`) |
| Current store | Airtable "Truck Driver Leads" *(to be retired)* |
| Classification LLM | Azure OpenAI, inside n8n AI Agent nodes |

## Domain vocabulary

- **New Lead / Existing Lead** — two VAPI assistants. An `assistant-request`
  webhook looks the caller's number up and routes to one of them.
- **Temperature** — lead urgency from stated readiness: HOT (≤3 days),
  MEDIUM (≤7), WARM (≤14), COLD (later). Note: Airtable spells the field
  `Temprature`.
- **Readiness** — how soon the driver can start.
- **logApplicantInfo** — the single VAPI tool. Collects name, location, phone,
  experience, readiness, preferred callback time; also performs the booking.
- **Postcode analysis** — reporting on where drivers are calling from. Currently
  parsed out of a free-text `Location` field; should become a real `Zip_Code`
  field on the Zoho candidate.

## Layout

```
config/vapi/     assistant + tool config, exported from live (secrets redacted)
config/n8n/      workflow JSON, exported from live (secrets redacted)
scripts/         export_config.py — re-export live config
docs/AUDIT.md    findings from the 2026-08-12 read-only audit
docs/ZOHO-SETUP.md  how to obtain and store the Zoho credentials
docs/learning/    learning track: one doc per step + glossary (owner is learning Python/SQL)
tasks/todo.md    prioritised work
```

`config/` is **generated**. Edit intent there, then deploy deliberately — do not
hand-edit and assume it matches live. Re-run `python scripts/export_config.py`
to resync and diff.

## Platform quirks — read before touching anything

- **Bare `python` is the wrong interpreter** on this machine (resolves to a
  hermes-agent venv without pytest). Use `py -3.11`. Existing tests use
  `unittest`, not pytest.

- **Two n8n instances.** `N8N_BASE_URL` (`n8n.accelentai.com`) is a copy where
  every workflow is inactive. Production webhooks are served from
  `accelentai.app.n8n.cloud`. Edits via the API key currently hit the inactive
  copy. Confirm which host you are changing before claiming a fix works.
- `N8N_BASE_URL` has a **trailing slash** — concatenating `/api/v1/...` yields a
  double slash and a 404. Strip it.
- **VAPI rejects the default Python urllib User-Agent with 403.** Send a
  browser/curl UA. `scripts/export_config.py` already does.
- VAPI sends tool arguments at both `message.toolCalls[0]` and
  `message.toolCallList[0]`. The workflows mix the two; standardise on
  `toolCalls[0]`.
- Zoho Recruit is OAuth-only — no API key. Access tokens last 1 hour and are
  derived from the refresh token; cache them.
- Zoho header name must be exactly `Authorization`. A trailing space silently
  yields 401 (this bug is live — AUDIT #6).

## Verify

```bash
py -3.11 -m unittest discover -s tests   # 32 tests, no network
node tests/js/test_cdl_helpers.js
python scripts/export_config.py     # re-export live config; diff must be clean
grep -rnE '1000\.[A-Za-z0-9]{10,}|[0-9a-f]{32,}' config/   # must return nothing
```

No automated test harness exists yet. Until one does, a change is only "done"
when a real test call has been placed and the resulting Zoho/Airtable record
inspected — not when the workflow saves without error.

## Safety

Deploys to VAPI or n8n change a system that answers real phone calls. Treat any
`PUT`/`PATCH`/`POST` to those APIs as a live side effect: get explicit approval,
and report real-call counts separately from dry runs.
