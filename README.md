# Frontline CDL Staffing: voice AI intake with a "no lead lost" backend

A voice agent answers calls from truck drivers (CDL drivers) who are looking for work. It collects
their details, books a recruiter callback, and hands the lead to the CRM (Zoho Recruit). Recruiters
work the leads from a web dashboard.

This is a **portfolio rebuild** of a system I delivered to a real client. The agency name is
fictional, every person and phone number in the data is fictional, and the client's own workflows
and data are not part of this repository.

- Public demo dashboard (fictional data, no CRM behind it): `https://cdl-demo.accelentai.com`
  (demo login on request)
- Case study (the story in one page): [`docs/CASE-STUDY.md`](docs/CASE-STUDY.md)
- Recording plan for the demo video: [`docs/RECORDING-PLAN.md`](docs/RECORDING-PLAN.md)

## 1. Business problem and outcome

**Problem.** A staffing agency gets calls from drivers at all hours, but recruiters work 9 to 5.
A missed call is often a lost driver: they call the next agency. The details that did get written
down lived in free text, so nobody could sort leads by urgency or report on where drivers call from.

**What the system does now**

- Answers every call with a voice agent and asks the same questions every time: name, city, state,
  ZIP code, years of experience, how soon they can start, best phone, callback time.
- Saves the answers in fixed fields, not free text. How soon a driver can start becomes a
  **temperature**: HOT (within 3 days), MEDIUM (7), WARM (14), COLD (later). The ZIP code is its own
  field, so "where are drivers calling from" is a simple query.
- Books a 15-minute recruiter callback in Google Calendar, only at a free weekday time, and checks
  that the saved event really belongs to this call before telling the caller it is booked.
- Recognises returning callers and uses a shorter script for them. A returning caller who books
  again has their earlier upcoming callback replaced (one upcoming callback per phone number).
- Gives recruiters a dashboard: a "To do" list ordered by who to call first, the applicant's
  details, the call recording and transcript, and a way to correct a wrong field.
- Keeps every lead even when the CRM is down (section 4).

What I can claim is what the repo records show (test calls and a drill, section 6). The rebuild has
not handled real production traffic, so it has no real-world conversion numbers.

## 2. How a call flows

```
 Driver's phone
      |
      v
  VAPI voice agent  ---- (1) "who is calling?" ---->  n8n CDL 01 Routing
  (New Lead or                                        looks in our database first, then Zoho
   Existing Lead)  <--- picks the assistant ---------
      |
      | (2) logApplicantInfo tool
      v
  n8n CDL 02 Intake  --- POST /calls (API key) --->  Python API (FastAPI)
      |                                                 |  one transaction:
      |                                                 |  call row + applicant + outbox row
      |                                                 v
      |                                              Postgres (Supabase)
      |                                                 ^
      | (3) booking                                     |  reads pending outbox rows
      v                                                 |
  n8n CDL 03 Booking ---> Google Calendar            Outbox worker ---> Zoho Recruit
                                                     (retries with growing waits)
  (4) end of call
  VAPI report ---> n8n CDL 04 Post-Call ---> POST /call-reports (summary, transcript)

  Recruiter ---> dashboard (served by the same Python API, login required)
```

## 3. n8n and VAPI design

- **Two assistants, one tool.** "New Lead" runs the full intake; "Existing Lead" greets the caller by
  name and mostly handles moving a callback. Both use one tool, `logApplicantInfo`, which saves the
  details and books the callback.
- **Routing before the call starts.** VAPI asks n8n which assistant to use (an `assistant-request`).
  VAPI drops the call if there is no answer within 7.5 seconds, a limit that cannot be changed. So
  CDL 01 asks our own database first (2 s), then Zoho (4 s, retries off), and treats a failed lookup
  as a new caller. "Existing" means anyone who has called us, even if the CRM copy is not made yet.
- **Four small workflows, not one big one** (CDL 01 Routing, 02 Intake, 03 Booking, 04 Post-Call), so
  each part can be tested and debugged on its own.
- **The agent judges, the code checks.** The voice agent picks one of four fixed readiness answers;
  the code maps them to a temperature and anything else becomes UNKNOWN, never a silent COLD. ZIP
  must be exactly 5 digits; times are checked against business hours and US federal holidays.
- **Why n8n stays.** n8n is good glue: calendar calls, emails, routing, steps a non-engineer can read
  and edit. It is not where correctness should live, so the parts that must never lose data moved
  to Python (next section). This split is deliberate.

## 4. Why a Python API, Postgres and an outbox worker were added

The first version wrote straight from n8n to Zoho during the call. Two real problems showed up in
testing:

1. **If Zoho was slow or down, the lead was at risk** while the caller was still on the line.
2. **Two writers made duplicates.** n8n and the new worker both wrote to Zoho one second apart, and
   one call produced two Zoho candidates (found 2026-10-08). n8n's Zoho search by `phone=` never
   matched, so it could not see the other record.

The fix is one rule: **save to our own database first; the CRM copy happens afterwards.**

- `POST /calls` saves the call, the applicant and a delivery slip (the **outbox row**, "send this to
  Zoho") in one database transaction, so either all three are saved or none is.
- A background courier (the **outbox worker**) picks up pending rows and sends them to Zoho. If Zoho
  fails it waits and tries again (**backoff**): 30 s, 60 s, 120 s ... never more than 15 minutes,
  and it never gives up on a temporary error. Two workers never take the same row
  (`FOR UPDATE SKIP LOCKED`).
- The worker is the **only** Zoho writer, and it finds an existing candidate by phone first (the
  **dedupe**), so a lead arrives exactly once.
- A repeated save of the same call is recognised (same call id) and does not create a second row
  (the endpoint is **idempotent**). Missing or bad details are saved anyway and flagged
  `needs_review`; they are never dropped.
- The caller is told "saved" only after the API confirms the save. If the save fails, the agent says
  it could not save the details and asks them to call back (tested live 2026-10-09 with the API
  stopped).

**The drill (2026-10-09, runbook in [`docs/B2-CRM-DOWN-DRILL.md`](docs/B2-CRM-DOWN-DRILL.md)).**
I pointed the worker at a Zoho address that can never answer and placed 2 real web calls. Both were
saved, both callers were told "saved and booked", and the outbox rows stayed `pending` with rising
waits. 0 writes reached Zoho. After restoring Zoho, both rows went `sent` on their own (after 5
and 6 tries). Result: 1 candidate and 1 note each, no duplicates, 6 calls = 6 sent, 0 pending,
0 failed.

## 5. Recruiter dashboard

Served by the same FastAPI app (no separate frontend). Pages: Today's overview, To do, Applicants,
Call activity, Analytics, applicant detail.

- **To do**: one row per person. Problems come first (needs review, Zoho sync failed), then HOT to
  COLD, then the earliest callback. Mark as called, with Undo.
- **Applicant page**: details, call history, transcript, recording (a fresh signed link each time,
  the VAPI key stays on the server), follow-up status, change history.
- **Corrections** save to Postgres and queue an outbox row, so Zoho is updated by the same worker.
- **Sync status is visible**: "Waiting to send", "Sent to Zoho", "Zoho sync failed".
- **Logins**: two roles, `recruiter` and `admin`. Passwords hashed with argon2id; a per-user counter
  (`session_version`) logs out every earlier session at once after a password change. Login and
  write rate limits, and an audit log of who changed what.
- **Public demo**: a separate container and database with 39 fictional applicants, a nightly reset,
  no Zoho/VAPI/n8n keys and no outbound internet.

## 6. What was verified, and what was not

Verified means a real check against the live system, recorded in [`tasks/todo.md`](tasks/todo.md).

| Area | Verified | Not verified |
|---|---|---|
| Save first, CRM after | Real calls saved, outbox `sent`, one Zoho candidate (2026-10-08, 10-12) | |
| CRM-down drill | 2 calls during a Zoho outage, both delivered after, no duplicates (2026-10-09) | Not yet recorded on video |
| Save failure path | API stopped: agent said it could not save (2026-10-09) | |
| Caller lookup | Routing calls on live: known caller found in 1.1 s, unknown 3.1 s (2026-10-24) | Zoho fallback with the API switched off |
| Returning-caller details | Lookup and routing on live; mocked voice simulations (2026-10-26) | A Zoho-only caller |
| Callback time replay fix | 427 API tests, deployed (2026-10-26) | A real call where the first time is rejected and the second accepted |
| Callback replacement, moving vs. cancelling | First real test call: conversation, calendar replacement and dashboard looked right (2026-10-27) | |
| Recruiter emails | Two real Existing Lead calls (move, then cancel request): both emails arrived (2026-10-28, reported by the owner) | Executions not inspected independently |
| Dashboard corrections to Zoho | Unit tests with a fake Zoho | A correction reaching the real Zoho on live |

## 7. Known issues

Listed honestly. None of them loses a saved lead.

- **Webhook authentication is paused.** n8n's webhooks do not yet check a shared secret from VAPI.
  The first attempt (attaching a VAPI credential to the phone number, the tool and both assistants
  on 2026-10-27) made the next real call fail with "number unavailable". All four changes were
  rolled back and the next call worked. The cause is not confirmed. The next attempt will be tested
  on a path that cannot block real calls, with an independent review before it is enforced. The
  API itself does require an API key from n8n.
- **Time zone after November 1, 2026.** The business time zone is `America/Vancouver`. In current
  time-zone data, British Columbia stays on UTC-7 all year from November 2026 (checked locally:
  2026-11-15 shows `-0700`), while US Pacific (Washington, Oregon, California) moves to UTC-8. The
  agent still says "Pacific", so from November a driver in Seattle would hear a callback time that is
  one hour off their local clock. Not fixed yet: the fix is a business decision (which clock the
  recruiters use) before it is a code change.
- **Calendar events booked before 2026-10-27 are not replaced.** The "one upcoming callback per phone"
  rule finds earlier events by a phone tag added in that release. Older events have no tag, so a
  caller with an old booking can end up with two.
- **The "cancel request" label is judged by the AI.** VAPI's end-of-call analysis decides whether a
  call was a cancel request; that triggers the recruiter email. How reliably it labels this has not
  been measured.
- **Correcting city or state does not fix the ZIP.** The "keep what a recruiter corrected" rule works one
  field at a time. If a recruiter fixes the city, a later call can still update the ZIP, so a record can
  briefly show a city and a ZIP from different places. A recruiter has to fix both.
- **No cancel tool, on purpose.** Owner decision: a cancelled callback is often a lost lead. The
  Existing Lead agent offers to move the callback first; if the caller still wants to cancel, it
  notes the request and recruiters get an email. The calendar event is not removed automatically.
- **DNS blips on the server.** The worker once logged about 12 "failed to resolve host" errors for
  the database (2026-10-08), all self-recovered. It could not be reproduced (280 lookups, 0 failures).
  The API now retries the connection 3 times; the root cause is unknown.
- **Generated n8n workflows differ from live.** `config/n8n/production/modular/` is older than the
  live, partly hand-edited workflows (for example, it lacks the API key auth). Live changes are made
  with small, drift-checked patches, never by redeploying that suite.
- **n8n keeps full run history.** Every n8n run stores its inputs and outputs, including caller
  details, with no time limit set yet.
- **The booking-outcome note no longer goes to Zoho.** The database-first change removed n8n's Zoho
  writes, including the "Callback" note. Zoho still gets the intake note (from the worker) and the
  post-call note; the booking outcome itself is in the database and the calendar.

## 8. Run the tests

On Windows use `py -3.11` (see `CLAUDE.md`). No test calls the network.

```bash
py -3.11 -m unittest discover -s tests      # workflow builders and contracts
node tests/js/test_cdl_helpers.js           # n8n helper code (phone, ZIP, callback time)
py -3.11 scripts/run_api_tests.py           # API tests against a local Postgres in Docker
```

The API tests need Docker Desktop with the `api-db-1` container running (`api/docker-compose.yml`)
and the API's own virtual environment (`api/requirements-dev.txt`). Run only one API test run at a
time: each run drops and recreates the shared test database. Last recorded results: 525 API tests
on the release worktree (2026-10-26), 76 workflow and contract tests (2026-10-27).

## 9. Repository layout

```
api/app/          FastAPI app: intake, call reports, caller lookup, worker, Zoho client, dashboard
api/migrations/   plain SQL migrations (001 to 012) and a small runner
api/tests/        API tests (pytest, real Postgres)
config/vapi/      assistant prompts and config, exported from live, secrets removed
config/n8n/       workflow JSON, exported from live, secrets removed
workflow-src/     helper code embedded in the n8n Code nodes
scripts/          deploy, drift-check, status and cleanup scripts (dry run by default)
docs/             audit, runbooks, plans, case study, learning notes
tasks/todo.md     the work log, with real actions and verification for each release
```

## 10. Who did what

I am learning Python and SQL through this project, and I built it with Claude Code as my pair.

- **My decisions**: the business rules and the scope. For example, save first and CRM after, the
  temperature buckets, ZIP as its own field, Vancouver as the business time zone, "existing caller"
  means anyone who has called, one upcoming callback per phone, no cancel tool, costs out of the Zoho
  note, the public demo with fictional data only, and approving every live change.
- **Claude Code's work**: most of the code, tests and deploy scripts, the drift checks before each
  live change, and the simulated test calls. My notes on what I predicted, decided and debugged
  myself are in [`docs/learning/interview-story.md`](docs/learning/interview-story.md).
