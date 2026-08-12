# Work plan

Findings and numbering come from `docs/AUDIT.md`.
Nothing below has been deployed — the audit was read-only.

## Phase 0 — decide and unblock (needs you, not me)

- [ ] **Rotate the Zoho client secret + refresh token.** They were hardcoded in
      the n8n workflows and printed during the audit. `docs/ZOHO-SETUP.md` §3–4.
      *Blocks every Zoho task below.* (AUDIT #1)
- [ ] **Confirm which n8n host is production** and get an API key for it.
      Right now API edits land on the inactive copy. (AUDIT #4)
- [ ] **Confirm the business timezone.** Chicago, Los Angeles and New York are
      all implied by the current config. Everything gets normalised to one.
      (AUDIT #5)
- [ ] **Confirm the company name** — Frontline CDL Staffing vs Class A
      Solutions. (AUDIT #14)
- [ ] Decide: should the agent collect an **email address**? Without one, Zoho
      cannot deduplicate candidates. (AUDIT #13)

## Phase 1 — stop the bleeding (small, safe, high value)

- [ ] Fix `.env`: duplicate `VAPI_ASSISTANT_ID` → two named vars.
- [ ] Fix the trailing space in `"Authorization "` on the two Zoho update nodes.
      One character; currently voids every candidate status update. (AUDIT #6)
- [ ] Resolve the temperature enum contradiction — HOT/MEDIUM/WARM/COLD
      everywhere, delete `LOW`. (AUDIT #10)
- [ ] Make appointment length consistent (15 min) and let the node, not the LLM,
      own start/end. (AUDIT #11)
- [ ] Remove all `kbTool` references from both prompts, or build the tool.
      Delete the Scenario 3 example that demonstrates inventing job openings.
      (AUDIT #8)
- [ ] Attach an `endCall` tool to both assistants. (AUDIT #9)
- [ ] Delete Scenario 5's wrong business hours (7 AM–2 PM leftover). (AUDIT #5)
- [ ] Raise `transcriptionEndpointingPlan.onNumberSeconds` to ~0.7 s so the
      agent stops interrupting callers reading phone numbers and ZIPs.
      (AUDIT #17)
- [ ] Raise tool + server `timeoutSeconds` from 20 s. (AUDIT #15)

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
