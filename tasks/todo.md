# Work plan

Findings and numbering come from `docs/AUDIT.md`.
Nothing below has been deployed — the audit was read-only.

## Decisions (settled 2026-08-12)

- Company name: **Frontline CDL Staffing** (CDL, not CDI).
- Business timezone: **America/Vancouver**, Mon–Fri 9 AM–5 PM Pacific.
- Build/deploy target: **self-hosted `n8n.accelentai.com`** (the host the API
  key works against).
- The agent does **not** collect email. Candidate dedupe in Zoho Recruit must
  therefore key on phone number + `VAPI_Call_ID`, not Email.
- Nothing is in production — all of this is draft, so changes can go live.

## Phase 0 — credentials

- [x] Create and connect the server-based Zoho Recruit OAuth credential in the
      self-hosted n8n credential store. Verified with read-only module and
      Candidate-field API requests on 2026-08-12. (AUDIT #1)
- [ ] Confirm the previously exposed Zoho client secret was rotated. The new
      workflow never embeds a client secret or refresh token.

## Phase 1 — VAPI assistants ✅ DONE, deployed and verified

- [x] Company name unified to Frontline CDL Staffing; "Class A Solutions"
      removed. (AUDIT #14)
- [x] Timezone unified to `America/Vancouver`; hours stated once as Mon–Fri
      9 AM–5 PM. Deleted the stray 7 AM–2 PM scenario. (AUDIT #5, partial —
      n8n side still Chicago)
- [x] All `kbTool` references removed; replaced with an explicit "you have no
      knowledge base, never invent an opening" rule. Deleted the worked
      hallucination example. (AUDIT #8)
- [x] `endCall` tool attached to both assistants. (AUDIT #9)
- [x] `onNumberSeconds` 0.3 → 0.7, `waitSeconds` 0 → 0.4, `stopSpeakingPlan`
      added, so the agent stops cutting callers off mid-digit. (AUDIT #17)
- [x] `server.timeoutSeconds` 20 → 30. (AUDIT #15)
- [x] `summaryPlan` + `structuredDataPlan` + `successEvaluationPlan` enabled, so
      a mid-call hangup still yields a structured record. (AUDIT #21)
- [x] `model.temperature` pinned to 0.3; assistant name typo "Exisiting" fixed.
- [x] Prompt now insists on an explicit ZIP code and reads phone numbers back
      digit by digit (both feed Phase 3 dedupe and postcode analysis).

Not yet done, deliberately deferred so the tool contract and its consumer
change together in Phase 3:

- [x] Prepare the versioned `logApplicantInfo` tool contract with `city` /
      `state` / `zipCode`. Applied to the shared live VAPI tool on 2026-08-13.
- [ ] Fix `.env`: duplicate `VAPI_ASSISTANT_ID` → two named vars (yours to do;
      I don't edit `.env`).

## Phase 2 — n8n rebuild on the self-hosted instance

- [x] Replace manual Authorization headers with the saved Zoho OAuth
      credential. (AUDIT #6)
- [x] Resolve temperature deterministically as HOT/MEDIUM/WARM/COLD; remove
      the LLM classifier and contradictory LOW value. (AUDIT #10)
- [x] Make the workflow own a consistent 15-minute appointment. (AUDIT #11)
- [x] Enforce `America/Vancouver`, weekdays 09:00–17:00, and US federal
      holidays in deterministic code. (AUDIT #5)
- [x] Replace the 36-node monolith with four inactive single-responsibility
      workflows: Routing (5), Intake (17), Calendar Booking (15), and Post-Call
      Report (8). The obsolete remote monolith was removed after verification.
- [x] Repoint the VAPI tool + both assistant `server.url` values at the
      self-hosted Intake and Post-Call webhooks.

## Phase 2 — make it reachable

- [x] Provision VAPI number `+1 206-944-1294` and point its `server.url` at the
      self-hosted `assistant-request` webhook with no fixed assistant, enabling
      dynamic New/Existing routing. (AUDIT #2)
- [x] Normalise phone numbers to E.164 properly; key the caller lookup off
      `call.customer.number` on both write and read. (AUDIT #7)
- [ ] Place a real test call and inspect the resulting record.

## Phase 3 — Zoho Recruit becomes the system of record

- [x] Run the schema discovery in `docs/ZOHO-SETUP.md` §7. Candidates has 52
      fields, including `Phone`, `City`, `State`, `Zip_Code`, and
      `Experience_in_Years`; `VAPI_Call_ID`, `Temperature`, callback, and
      calendar-event fields do not yet exist. Verified 2026-08-12 through the
      self-hosted n8n OAuth credential.
- [ ] Create the optional custom fields in §7, especially `VAPI_Call_ID`,
      `Temperature`, callback time, and calendar event URL. `Zip_Code` already
      exists as a standard Candidate field.
- [x] Move the Zoho credentials into the n8n credential store. (AUDIT #1)
- [x] Replace the four unfinished workflows with one generated modular suite:
      three stable public webhook workflows plus an internal Calendar Booking
      subworkflow. (AUDIT #3)
- [ ] Candidate upsert: send `Email`, set `duplicate_check_fields`, handle
      single-word names, drop `Note_Content` from the Candidates payload.
      (AUDIT #13)
- [x] Replace legacy `driverLocation` with required `city`, `state`, and
      `zipCode` tool parameters so postcode analysis reads real Zoho fields.
- [x] Write the transcript and call metadata to Zoho `Notes` on the candidate,
      replacing the Airtable "End of Call Report" table.
- [ ] Cache the Zoho access token for its full hour. (AUDIT #22)

## Phase 4 — booking correctness

- [x] Check Google Calendar FreeBusy before event insertion and use a
      deterministic event ID to make duplicate VAPI delivery idempotent.
      (AUDIT #12)
- [x] Single timezone end to end: prompt, business-hours code, calendar,
      Zoho. (AUDIT #5)
- [x] Return the confirmed time in the tool response so the agent can read it
      back instead of reciting one it merely remembers.
- [ ] Mirror the booking onto the Zoho candidate (`Callback_Time`,
      `Calendar_Event_URL`).

## Phase 5 — robustness

- [x] `onError` + retry on every external call; always respond to VAPI even on
      failure, so the caller hears a graceful message rather than dead air.
      (AUDIT #16)
- [ ] Enable `structuredDataPlan` so a caller who hangs up mid-intake still
      produces a usable record. (AUDIT #21)
- [ ] Standardise on `toolCalls[0]`; single source for `Call ID`.
      (AUDIT #18, #19)
- [ ] Escape `filterByFormula` inputs. (AUDIT #20)
- [ ] Fix `Experience_in_Years` so "1–2 years" and "2+ years" differ.
      (AUDIT #23)
- [ ] Retire Airtable as an input once Zoho is authoritative.

## Review

- Local helper assertions pass.
- Twenty-two helper, architecture, deployment, security, and concurrency tests
  pass.
- Invalid-intake and routing smoke tests passed without creating Zoho or
  Google records.
- Four inactive self-hosted drafts are installed with 5/16/15/8 nodes.
- Modular smoke tests pass for routing, invalid intake, post-call acknowledgement,
  native booking execution, same-slot cancellation restoration, and cleanup.
- A labelled fictional Zoho Recruit Candidate (`Loom Demo Candidate`, ID
  `870474000000581004`) was created through the real modular intake path. Its
  fields plus one intake Note and one outside-hours callback Note were read
  back successfully; the Saturday request created no Calendar event.
- Twenty-five Python workflow/deployment regression tests and the JavaScript
  helper assertions pass. The inactive remote node counts are 5/17/15/8 and no
  temporary workflows remain.
- Google Calendar OAuth is connected on self-hosted n8n. FreeBusy, event
  create, event get, and event cleanup passed through the same credential and
  HTTP-request pattern used by production.
- Production safeguard: enforce unique phone/dedupe in Zoho before activation.
