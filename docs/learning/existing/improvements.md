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
| W6 | *(observed, to confirm in U3)* *Prepare Booking Input* throws if the intake Note fails, and that node has no `onError`. The run would stop before any Respond node, so VAPI likely gets an error instead of a spoken fallback. | 02 → *Prepare Booking Input* | Caller may hear a tool error even though the Candidate *was* saved | Verify in U3, then decide |
| W7 | Nodes reference each other by name (`$('Normalize Route Request')`), so renaming one breaks others silently until runtime. | all workflows | Fragile edits | Mitigated: workflows are generated from `scripts/build_modular_workflows.py` and tested |
| W8 | The Zoho access token isn't explicitly cached (AUDIT #22). The n8n OAuth credential handles refresh itself, so check this in U6/U7. | credentials | Possible rate-limit pressure | Step 7 (token cached for 1 h) |
