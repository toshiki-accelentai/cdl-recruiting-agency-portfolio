# Work plan

## Production-grade + learning track (started 2026-09-21)

Coach's brief: Python API → SQL database → CRM, with duplicate / missing-info /
failed-API handling and a "CRM is down, no lead lost" demo; then a recruiter
dashboard. Every step ships a learning doc. Index and progress checklist:
`docs/learning/README.md`. Full plan: Phase 0 → U (understand existing) → A
(receive + store, Postgres on Supabase) → B (outbox worker, resilience) → C
(dashboard). All data fictional; own VAPI + Zoho accounts only.

- [x] Phase 0: removed accidental nested `docs/.git` (backed up to the session
      scratchpad), committed baseline on branch `feat/python-api`.
      Baseline: 32 unittest tests pass, JS helper assertions pass (no network).
- [x] Phase U (U1–U8) done 2026-10-03. U9 checkpoint skipped.

**Ship-first plan (2026-10-03, mentor guidance):** ~60% code understanding is
enough. Build fast, start applying, and save deep study for while waiting on
interviews. Each chunk: Claude implements test-first → short doc (what it
does, data flow, key design decision, 2–3 interview talking points) → **one
debug drill** the learner solves alone (a planted bug or a real failure to
diagnose). Order is strict: A → B → C → apply.

- [x] **A1** (built + 16 tests green 2026-10-03; debug drill done) Python API skeleton: `POST /calls` receives a VAPI-shaped intake
      payload and saves it to Postgres in one transaction (schema + migration).
      Stack agreed 2026-10-03: FastAPI; local Postgres in Docker for dev/tests
      (moves to Supabase at B3); plain `.sql` migration files + a tiny runner
      (no Alembic); pytest in its own project venv (existing `unittest` suite
      untouched). Fixture payload shape:
      `docs/learning/existing/samples/u3-john-real-shape.json`. No live
      VAPI/n8n/Zoho changes until A3. Deliverables: endpoint + tests against
      real Postgres + short doc + one planted-bug debug drill.
- [x] **A2** (built + 25 tests green; debug drill done 2026-10-05) Duplicate calls (same call ID / phone) and missing info handled: replay returns 200 `duplicate:true`; one applicant per phone, merge only provided fields; invalid phone / missing name saves the call with `needs_review`. Migrations 002-003.
- [x] **A3** (done 2026-10-06) Point Applicant Intake at the API (n8n keeps routing,
      booking and post-call); one real fictional test call, verified in the DB.
      API + its own Postgres run on hermes-vps (`/opt/cdl-api`, no published ports,
      reachable only from n8n over `n8n_app`). Live Intake got a side branch
      `Save to Database API` (17 -> 18 nodes, surgical patch via
      `scripts/deploy_intake_api_branch.py`; the live Intake was hand-edited, so the
      generated suite was NOT redeployed). Real-action counts: 1 synthetic webhook POST
      (no Zoho/Calendar writes, rejected by n8n as past_time but saved in the DB),
      1 real VAPI web call (execution 8444, all 16 nodes success; DB call_id 2).
      Not inspected: the resulting Zoho candidate / Calendar event.
      **Follow-ups:** (1) sync `build_modular_workflows.py` Normalize Intake with the
      live hand-edited version (callback validation lives in that node); (2) add a
      shared-secret header on the API (B3); (3) set Intake + Booking back to inactive
      after testing (default-inactive rule); (4) VAPI routing (CDL 01) and post-call
      (CDL 04) still inactive.
- [ ] **Zoho dedupe bug (found 2026-10-07 while smoke-testing B1):** Zoho Recruit's
      `/Candidates/search?phone=...` never matches an existing candidate (verified live:
      `phone=` in 3 formats -> 204; `criteria=(Phone:equals:+1...)` -> match). The n8n node
      `Find Candidate for Intake` uses `phone=`, so repeat callers probably create duplicate
      candidates there. The Python client now uses `criteria`. Fix the n8n node the same way
      (live Intake is hand-edited: patch surgically, dry-run first) or retire that path.
- [ ] **B1** Zoho client + outbox worker: DB row first, CRM sync after.
      **Status 2026-10-07: code done, deployment pending.** Done: outbox table written in the
      same transaction as the call; `app/zoho.py` (retry/fail classification, token cache, 401
      refresh, `criteria` search); `app/worker.py` (SKIP LOCKED, capped 15-min backoff forever);
      RLS migration 006; 75 tests, no network. Verified against REAL Zoho twice via
      `scripts/smoke_test_outbox_worker.py --apply` (1 candidate `B1 Smoke Driver`
      870474000000665002, 2 notes, dedupe by phone confirmed).
      **2026-10-07 later: steps (1)-(3) DONE.** Supabase project exists (eu-central-1 Session
      pooler, :5432), connection verified, migrations 001-006 applied, RLS on for all 4 tables,
      0 policies, 0 rows. Connection string lives in `api/deploy/.env.supabase` (git-ignored) and
      the password in the user's password manager. Check anytime with
      `api\.venv\Scripts\python.exe scripts\check_supabase_connection.py` (prints no secrets).
      **2026-10-07 even later: step (4) DONE and verified (read-only checks on the server).**
      `/opt/cdl-api/compose.yaml` now = `cdl-api` (on `n8n_app`, DB = Supabase pooler) + `worker`
      (default network, `.env` with DATABASE_URL + ZOHO_*). Migrations "up to date", worker log
      "outbox worker started", n8n -> `http://cdl-api:8000/docs` OK, port 8000 not published.
      Old local DB container `cdl-api-db-1` is STOPPED (not deleted); its data stays in
      `/opt/cdl-api/pgdata` (47M). Backups on the server: `.env.old-local-db`,
      `compose.yaml.old-local-db`. Real-action report: container swap + 2 server files only;
      0 Zoho writes, 0 calls.
      **Access quirk:** `hermes-vps` does not resolve from this PC; use
      `ssh -i ~/.ssh/hermes-hetzner hermesadmin@62.238.51.45`. Claude Code's auto-mode
      classifier blocks remote *writes* even with allow rules in `.claude/settings.local.json`;
      read-only ssh works, writes are handed to the user's PowerShell.
      REMAINING: (5) end-to-end real call (n8n Intake + Booking must be activated for it, then
      deactivated again).
      **Plan for (4), approved in principle, ask again before each live step:**
      a) edit `api/deploy/compose.yaml`: remove the local `db` service and its network use; give
         `cdl-api` `DATABASE_URL` from the server `.env`; add a `worker` service (same image,
         `command: python -m app.worker`, `env_file: .env`, networks: internal not needed, no ports);
         keep `n8n_app` for the API only. Stop (do NOT delete) the old `db` container/volume.
      b) secrets reach the server by file copy, never printed: `DATABASE_URL` from
         `api/deploy/.env.supabase`; `ZOHO_CLIENT_ID/SECRET/REFRESH_TOKEN` from the repo-root `.env`;
         write to `/opt/cdl-api/.env` with `chmod 600`, owner hermesadmin.
      c) copy `api/app`, `migrations`, `requirements.txt`, `Dockerfile` to `/opt/cdl-api/src`,
         `sudo -n docker compose up -d --build`, then verify: both containers healthy, API log shows
         migrations up to date against Supabase, worker log "outbox worker started", n8n container
         can reach `http://cdl-api:8000/docs`, port 8000 not reachable from the internet.
      d) do NOT move the 2 old test rows from the server DB to Supabase (practice data).
      Real-action report: server file changes + container swap only; 0 Zoho writes, 0 calls.
      Lessons from this session: never put secrets through error messages (use
      `scripts/check_supabase_connection.py` style checks); the user's shell is PowerShell 5.1;
      the user prefers Japanese explanations with analogies, one step at a time.
      (old plan text follows) **Next (in order):** (1) user creates a Supabase project (Session pooler string,
      port 5432, NOT 6543) and saves `DATABASE_URL=...` in `api/deploy/.env.supabase`;
      (2) read-only connection check; (3) apply migrations 001-006 to Supabase (confirm first),
      verify RLS on; (4) deploy API + worker to hermes-vps (`/opt/cdl-api`) pointing at Supabase,
      worker gets ZOHO_* in the server `.env` (chmod 600); add a `worker` service to
      `api/deploy/compose.yaml` and drop the local `db` service there; (5) end-to-end: one real
      call -> Supabase row -> Zoho. Then B2 (CRM-down demo, record it).
      Server: `hermesadmin@hermes-vps`, docker needs `sudo -n`. n8n Intake + Booking must be
      deactivated again after any test window (currently inactive).
- [ ] **B2** "CRM is down" drill: break Zoho, take calls, restore, show no
      lead lost. **Record it — this is the headline interview demo.**
- [ ] **B3** Logging/observability + deploy.
- [ ] **C** Recruiter dashboard (review summaries, correct info, track
      follow-ups). Planned once B2 is recorded.
- [ ] **Apply.**
- Deferred until after applying: U9 checkpoint, deep walkthroughs, concept
  checks.

**Open decision, revisit when planning Phase A/B:** how much of n8n survives?
Not a full replace — this is a portfolio piece aimed at companies that run n8n
as their main automation tool, so n8n stays visible in the finished system.
The real question is scope: keep n8n only for the pieces where it's a genuine
fit (glue/orchestration, non-engineer-editable steps, correctness doesn't
depend on it), and move to the Python backend only what needs real
correctness guarantees (Applicant Intake, per W1/W6/W9/W10/W11 — this is
already the plan). Whatever the final split is, it should be something we can
explain and defend as a deliberate call, not an accident of how the build
happened — that explanation is itself part of the portfolio story.

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
  **Superseded 2026-09-23, then reverted same day**: the user briefly
  activated all four modular workflows on the self-hosted instance and ran a
  real fictional test call through them (see Phase 2 below), then
  deactivated all four again the same day. Re-verify active/inactive state
  directly before assuming either way — don't trust this note either, it
  will go stale.
- **Operating rule (settled 2026-09-23): default to inactive.** Activate a
  workflow only for a deliberate test/demo window, then deactivate again
  immediately after. Reasons: (1) the live VAPI number `+1 206-944-1294` can
  receive real calls from strangers, not just intentional tests, which would
  write real (non-fictional) callers' data into this portfolio's Zoho/Calendar
  accounts; (2) idle active time still accrues VAPI/telephony cost; (3) the
  system still carries known unresolved correctness bugs (W1, W6, W9, W10,
  W11 in `docs/learning/existing/improvements.md`) and no durable storage yet
  (Phase A), so a real call hitting one of those bugs right now has no
  recovery path. Revisit this rule once Phase A/B land.

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
- [x] Place a real test call and inspect the resulting record. Done
      2026-09-23 by the user directly (not through this session): a VAPI
      web-widget call ("John Smith," fictional, Tampa FL) hit the live
      `webhook/cdl/log-applicant` URL in `executionMode: "production"`,
      confirming CDL 02 is active and reachable. Sample payload saved at
      `docs/learning/existing/samples/u3-john-real-shape.json` (trimmed of
      call-session secrets like `listenUrl`/`controlUrl`). Resulting Zoho
      record not yet inspected here — do that before checking this off as
      fully verified end-to-end.

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
