# Weaknesses found while reading the existing system

A running list, added to during Phase U. Each item: what, where, impact, and
which planned step fixes it. This becomes the "why I built the Python API"
section of `../interview-story.md`.

Status: **observed** = seen in the config/code, **confirmed** = reproduced.

| # | Weakness | Where | Impact | Fixed by |
|---|---|---|---|---|
| W1 | No durable store of lead details outside Zoho. If Zoho fails during intake the caller hears "a recruiter will follow up", but the details live only in VAPI's call log. Successful n8n executions aren't saved (`saveDataSuccessExecution: none`). | 02 Intake → *Respond Candidate Failure* | Lead lost during a CRM outage | Steps 5 and 8 (Postgres + outbox) |
| W2 | Post-call replies 200 *before* writing Zoho, so VAPI never retries. If Zoho is down, the transcript and summary are lost. | 04 → *Acknowledge Post Call* | Transcript lost | Step 5 (commit, then 200) plus Step 8 |
| W3 | A new caller who hangs up before the tool call produces nothing. Post-call finds no Candidate, and the IF false branch is unconnected. | 04 → *Candidate Found?* | Partial lead lost, even though the structured data was available | Steps 5–6 (store the partial lead as `needs_review`) |
| W4 | Placeholder phone `+10000000000` is used to avoid an empty-search error. | 01 and 04 search URLs | Hides a missing phone and makes a pointless API call | Step 6 (explicit missing-field handling) |
| W5 | Dedupe is search-then-create. Two calls from the same phone at once can both see "not found" and both create a record. There's no uniqueness enforced in Zoho (AUDIT #13 is still open). | 02 → *Find Candidate* → *Write Candidate* | Duplicate candidates | Step 5 (`UNIQUE(phone_e164)` in Postgres plus upsert) |
| W6 | **Half-confirmed (U3).** *Prepare Booking Input* throws if the intake Note fails, and that node has no `onError`. Proven: no `onError` in the JSON; the code throws when run locally in Node; no Respond node is reachable after it. **Still open:** the actual HTTP reply VAPI gets (expected 500, no `results`) needs the U3 exercise on an inactive copy. | 02 → *Prepare Booking Input* | Caller may hear a tool error even though the Candidate *was* saved, and the calendar is never booked | Finish the U3 exercise, then make a failed note non-fatal or route it to a Respond node |
| W7 | Nodes reference each other by name (`$('Normalize Route Request')`), so renaming one breaks others silently until runtime. | all workflows | Fragile edits | Mitigated: workflows are generated from `scripts/build_modular_workflows.py` and tested |
| W8 | The Zoho access token isn't explicitly cached (AUDIT #22). The n8n OAuth credential handles refresh itself, so check this in U6/U7. | credentials | Possible rate-limit pressure | Step 7 (token cached for 1 h) |
| W9 | *(observed, U3)* Retry budget is longer than VAPI's wait. Each Zoho node: 3 tries × 10 s timeout + 2 × 1 s = 32 s worst case, and intake makes 3 Zoho calls before replying. VAPI's `timeoutSeconds` is 30. | 02 HTTP nodes vs `config/vapi/tool.logApplicantInfo.json` | When Zoho is *slow* (not down) VAPI gives up while n8n keeps working; the write may still land | Step 8 (durable write, short timeouts) |
| W10 | *(observed, U3)* A failed Zoho search is treated as "not found". *Build Candidate Write Request* sees no `data`, picks `POST`. | 02 → nodes 5 and 6 | A brief search failure can create a duplicate candidate | Step 5 (`UNIQUE(phone_e164)` plus upsert) |
