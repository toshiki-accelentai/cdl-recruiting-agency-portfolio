# Audit — Frontline CDL Staffing voice AI intake

Date: 2026-08-12. Method: read-only GETs against the live VAPI and n8n APIs.
Nothing was modified. Raw exports (secrets redacted) are in `config/`.

---

## What actually exists

Two VAPI assistants, one shared tool, and one n8n workflow doing the real work:

| Piece | ID | Status |
|---|---|---|
| Assistant "CDL Recruiting Agency - New Lead" | `6901a714…` | live config, **no phone number** |
| Assistant "CDL Recruiting Agency - Exisiting Lead" | `542bae1c…` | live config, **no phone number** |
| Tool `logApplicantInfo` | `41a0ca37…` | → `accelentai.app.n8n.cloud/webhook/264b4bd9…` |
| n8n "CDL Recruting Agency" | `uT4iroyZm4hr2zay` | **the only workflow VAPI calls** |

Four other CDL workflows exist (`CDL - Main`, `CDL - Database Checker`,
`CDL - Post Call Analysis`, `CDL Recruting Agency - Zoho integration`). They are
refactored/split copies with **different webhook paths**, so VAPI never reaches
them. Webhook-path → workflow map:

```
264b4bd9…  CDL Recruting Agency   <== logApplicantInfo tool
12574ace…  CDL Recruting Agency   <== assistant server (end-of-call-report)
3c1c3227…  CDL Recruting Agency       (assistant-request routing, unused)
0e3af326…  CDL - Main  +  CDL Recruting Agency - Zoho integration
b7554693…  CDL - Database Checker  +  CDL Recruting Agency - Zoho integration
643e4ccf…  CDL - Post Call Analysis + CDL Recruting Agency - Zoho integration
2a868047…  Zoho Integration
```

---

## P0 — blocking

### 1. Zoho credentials are hardcoded in plaintext in the n8n workflows
`config/n8n/cdl-main--zoho-variant.json`, node `GET Token`. `client_id`,
`client_secret` and `refresh_token` sit as literal `bodyParameters` values
rather than in the n8n credential store. Anyone with the n8n API key — which is
how I read them — can exfiltrate them, and they are copied verbatim into three
workflows.

They were printed to a terminal during this audit and must be treated as
compromised.

**Fix:** rotate the Zoho client secret and refresh token, move them into an n8n
*Header Auth* / *Generic OAuth2* credential, and reference the credential rather
than inlining values. Never re-inline. Same applies to the copies in
`cdl-recruiting-agency--zoho-integration.json` and `zoho-integration.json`.

### 2. The system is unreachable by phone
Neither CDL assistant has a phone number attached. Your two VAPI numbers point
at the massage-salon assistant and a "Billing Assistant". The
`Lead exists` / `Lead not exists` branch (webhook `3c1c3227…`) is an
`assistant-request` responder that picks which assistant answers based on an
Airtable lookup — but nothing invokes it, because that URL has to be set as the
**phone number's** `server.url`, and no number is configured.

So the new-vs-returning-caller routing that the whole two-assistant design rests
on has never run in production.

### 3. Production does not write to Zoho Recruit at all
The only workflow VAPI calls, `CDL Recruting Agency`, contains **zero** Zoho
nodes — 25 Airtable references, 2 Google Calendar, 9 Gmail, 0 Zoho. The Zoho
integration was built in a parallel copy (`CDL - Main`) that VAPI never calls.

Today the system of record is Airtable. The Zoho work is written but unwired.

### 4. Two n8n instances, and the one you have API access to is entirely inactive
`N8N_BASE_URL` is `n8n.accelentai.com`, where all **119** workflows report
`active: false`. VAPI calls `accelentai.app.n8n.cloud`, whose webhooks respond
"not registered for GET requests… did you mean POST?" — i.e. they *are*
registered and live.

Consequence: edits made through the n8n API with your current key land on the
inactive copy and have no production effect. This needs resolving before any
deploy, or fixes will appear to work and change nothing.

---

## P1 — correctness

### 5. Four different timezones and three different business-hour windows
| Where | Says |
|---|---|
| Assistant prompt, "Context" | Mon–Fri **9 AM–5 PM**, clock rendered in `America/Los_Angeles` |
| Assistant prompt, Scenario 5 | Mon–Thu **7 AM–2 PM**, Fri 7 AM–12 PM |
| n8n `Business hour check` | `America/Chicago`, **07:00–17:00** |
| n8n AI Agent booking rules | offsets `-04:00 / -05:00` = **America/New_York** |
| Google Calendar `toshiki@accelentai.com` | its own default TZ |

A caller who says "10 AM" can be validated against Chicago hours, booked at a
New-York-derived offset, and told Los-Angeles-relative business hours. Bookings
land at the wrong time. This is the single highest-impact functional bug.

Scenario 5's 7 AM–2 PM window is leftover copy from a different client's agent.

### 6. Zoho candidate updates silently fail — trailing space in a header name
`cdl-main--zoho-variant.json`, nodes `Update record` and `Update record3` send
the header `"Authorization "` (trailing space) instead of `"Authorization"`.
Zoho sees no auth header and rejects with 401. `Temperature`, `Status` and
`Calendar_URL` therefore never reach the candidate record. `Create Candidate`
and `Add Note` spell it correctly, which is why the bug is easy to miss.

### 7. The returning-caller lookup can essentially never match
`Phone number format` builds the stored number as `"+1" + <spoken digits>`. If
the caller says "plus one two zero six…" or the transcriber emits `(206)
555-1234`, you store `+1+1206…` or `+1(206) 555-1234`. But `Search records`
matches that field against `call.customer.number`, which VAPI supplies in clean
E.164 (`+12065551294`). The two formats rarely agree, so returning callers are
classified as new. Needs real E.164 normalisation, and the lookup should key off
`call.customer.number` on both write and read.

### 8. `kbTool` is referenced five times but does not exist
Both prompts instruct the agent to answer common questions with `kbTool` and
state "the only information you have exists in this system prompt or using the
'kbTool' tool". The assistants have exactly one tool: `logApplicantInfo`.

Worse, Scenario 3 in the prompt *demonstrates inventing an answer* — "yes, we do
have active positions in Oklahoma City and Tulsa". That is a worked example of
hallucination, on a recruiting line where a fabricated job opening is a real
liability. Either build the knowledge base tool or delete every reference and
route those questions to a callback.

### 9. `endCall` is referenced but not attached
Prompts say "Trigger the 'endCall' function instantly". No `endCall` tool is on
either assistant and `endCallPhrases` is unset, so the agent cannot hang up and
the call runs until the caller drops or VAPI times out.

### 10. The classifier's own output contract contradicts itself
AI Agent system message defines temperature as `HOT / MEDIUM / WARM / COLD` in
the categorisation rules, then declares under "CRITICAL OUTPUT FORMAT" that
valid values are `HOT`, `MEDIUM`, or `LOW`. `WARM` and `COLD` are unlisted;
`LOW` is never defined. The structured output parser will reject or coerce a
large share of real classifications.

### 11. Appointment length is 15 minutes and 30 minutes
The AI Agent prompt says "Always use 15 min time window" and instructs the model
to pass computed `start`/`end`. The `bookAppointment` node ignores that: `start`
and `end` are hardcoded expressions off the webhook, with `end = start + 30
minutes`. The model's computed values are discarded, so the DST-offset logic in
the prompt is dead code.

### 12. Nothing checks whether the recruiter is actually free
`bookAppointment` creates an event unconditionally. "Available / unavailable" in
the prompt is decided *only* by the business-hours code, never by calendar
free/busy. Two callers can book the same slot. There is no `getAvailability`
tool on the CDL assistants (one exists in the org for a different client).

### 13. Zoho upsert cannot deduplicate
`Create Candidate` POSTs to `/Candidates/upsert` with no `duplicate_check_fields`
and never sends `Email`. Zoho's default dedupe key on Candidates is Email, so
every call creates a new candidate. Also `Last_Name` is derived by splitting the
spoken name on a space — a caller who gives one word yields an empty
`Last_Name`, which Zoho rejects as a mandatory field. And `Note_Content` is
passed as a Candidates field although it belongs to the Notes module (the
separate `Add Note` node already does this correctly).

### 14. Two company names
The prompt's Role and `firstMessage` say **Frontline CDL Staffing**; the Context
line and the Existing-Lead wrap-up say **Class A Solutions**. The agent will use
both in one call.

---

## P2 — robustness and voice quality

15. **20 s timeout is too tight.** Both the tool and the assistant `server` use
    `timeoutSeconds: 20`, but the chain is webhook → Airtable search → Airtable
    upsert → business-hour code → LLM agent → Google Calendar → respond. An LLM
    call with a tool round-trip routinely exceeds that; the caller hears dead air
    and then a failure.
16. **No error handling anywhere.** No node sets `onError` or `retryOnFail`. Any
    transient Airtable/Zoho/Calendar blip returns nothing to VAPI, which the
    agent surfaces as a hang.
17. **Barge-in tuned to cut callers off.** `startSpeakingPlan.waitSeconds: 0`
    with `onNumberSeconds: 0.3` — a caller reading a 10-digit phone number or a
    ZIP pauses longer than 0.3 s between groups, so the agent interrupts
    mid-number. Raise to ~0.6–0.8 s for a digit-heavy intake.
18. **`Call ID` is populated from two different sources.** The lead upsert uses
    the `x-call-id` *header*; the end-of-call report uses
    `body.message.call.id`. If they ever differ the post-call row never joins its
    lead row.
19. **`toolCalls[0]` and `toolCallList[0]` are used interchangeably** within the
    same node mapping and between the node and the AI Agent prompt. Pick one.
20. **`filterByFormula` interpolates raw input** — an apostrophe in the value
    breaks the formula.
21. **Call analysis is switched off.** `summaryPlan` and
    `successEvaluationPlan` are both `enabled: false` and there is no
    `structuredDataPlan`. If the caller hangs up before the tool fires, you
    capture nothing but a raw transcript — no structured fallback.
22. **A new Zoho access token is minted on every call**, with no caching. Zoho
    throttles access-token generation; at volume this starts failing.
23. **`Experience_in_Years` mis-parses.** The regex maps "1–2 years" → `2` and
    "2+ years" → `2`, so the two are indistinguishable.

---

## Recommended target architecture

**Make Zoho Recruit the single system of record. Keep Google Calendar only as
the free/busy source.**

| Concern | Today | Target |
|---|---|---|
| Candidate record | Airtable `Leads` | **Zoho Recruit `Candidates`** |
| Call history / transcript | Airtable `End of Call Report` | **Zoho Recruit `Notes`** on the candidate |
| Booking | Google Calendar event | **Google Calendar (free/busy + event) mirrored to Zoho** |
| Postcode analysis | Airtable `Location` free text | **`Zip_Code` custom field on the Candidate** |
| Lead temperature | Airtable `Temprature` | `Candidate_Status` / custom `Temperature` field |

Rationale for the two places I would *not* go all-Zoho:

- **Keep Google Calendar for availability.** Zoho Recruit has no practical
  free/busy endpoint. Calendar's FreeBusy API is what makes #12 fixable. Write
  the event to Calendar, then store the event link and time on the candidate.
- **Drop Airtable entirely.** Right now it is a second source of truth that
  disagrees with Zoho. Postcode analysis is better served by a real `Zip_Code`
  field on the candidate than by parsing a free-text "city, state, zip" blob the
  LLM wrote. If you want Airtable's pivot UI, keep it as a read-only mirror, not
  as an input.

This also collapses the four half-finished CDL workflows into one.

**Verify before building:** the exact Zoho module API names available in *your*
org (whether `Interviews` and `Notes` are exposed, and which Candidate fields
are mandatory) depend on your Recruit edition. Confirm with
`GET {ZOHO_RECRUIT_API_DOMAIN}/recruit/v2/settings/modules` and
`.../settings/fields?module=Candidates` once the rotated token exists — see
`docs/ZOHO-SETUP.md`. I could not run this because it needs a token.
