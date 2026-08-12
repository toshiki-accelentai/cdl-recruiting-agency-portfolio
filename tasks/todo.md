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

## Phase 0 — needs you, not me

- [ ] **Rotate the Zoho Recruit client secret + refresh token.** They were
      hardcoded in the n8n workflows and printed during the audit.
      `docs/ZOHO-SETUP.md` §3–4. *Blocks Phase 3.* (AUDIT #1)

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

- [ ] Split `driverLocation` into `city` / `state` / `zipCode` on the
      `logApplicantInfo` tool schema.
- [ ] Fix `.env`: duplicate `VAPI_ASSISTANT_ID` → two named vars (yours to do;
      I don't edit `.env`).

## Phase 2 — n8n rebuild on the self-hosted instance

- [ ] Fix the trailing space in `"Authorization "` on the two Zoho update nodes.
      One character; currently voids every candidate status update. (AUDIT #6)
- [ ] Resolve the temperature enum contradiction — HOT/MEDIUM/WARM/COLD
      everywhere, delete `LOW`. (AUDIT #10)
- [ ] Make appointment length consistent (15 min) and let the node, not the LLM,
      own start/end. (AUDIT #11)
- [ ] Business-hours code: `America/Chicago` 07:00–17:00 → `America/Vancouver`
      09:00–17:00. (AUDIT #5)
- [ ] Repoint the VAPI tool + assistant `server.url` at the self-hosted host
      once the merged workflow is live there.

## Phase 2 — make it reachable

- [ ] Provision a VAPI phone number for CDL and point its `server.url` at the
      `assistant-request` webhook (`3c1c3227…`) so New/Existing routing runs at
      all. (AUDIT #2)
- [ ] Normalise phone numbers to E.164 properly; key the caller lookup off
      `call.customer.number` on both write and read. (AUDIT #7)
- [ ] Place a real test call and inspect the resulting record.

## Phase 3 — Zoho Recruit becomes the system of record

- [ ] Run the schema discovery in `docs/ZOHO-SETUP.md` §6 — confirm which
      modules and Candidate fields actually exist in this org.
- [ ] Create the custom fields in §7, especially `VAPI_Call_ID` and `Zip_Code`.
- [ ] Move the Zoho credentials into the n8n credential store. (AUDIT #1)
- [ ] Merge the four half-finished CDL workflows into one, wired to the webhook
      paths VAPI actually calls. (AUDIT #3)
- [ ] Candidate upsert: send `Email`, set `duplicate_check_fields`, handle
      single-word names, drop `Note_Content` from the Candidates payload.
      (AUDIT #13)
- [ ] Split `driverLocation` into city / state / `Zip_Code` at intake so
      postcode analysis reads a real field. Ask for the ZIP explicitly.
- [ ] Write the transcript and call metadata to Zoho `Notes` on the candidate,
      replacing the Airtable "End of Call Report" table.
- [ ] Cache the Zoho access token for its full hour. (AUDIT #22)

## Phase 4 — booking correctness

- [ ] Add a `getAvailability` tool backed by Google Calendar FreeBusy so slots
      are checked before they are offered. Today double-booking is possible.
      (AUDIT #12)
- [ ] Single timezone end to end: prompt, business-hours code, calendar,
      Zoho. (AUDIT #5)
- [ ] Return the confirmed time in the tool response so the agent can read it
      back instead of reciting one it merely remembers.
- [ ] Mirror the booking onto the Zoho candidate (`Callback_Time`,
      `Calendar_Event_URL`).

## Phase 5 — robustness

- [ ] `onError` + retry on every external call; always respond to VAPI even on
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

_(to be filled in as work lands)_
