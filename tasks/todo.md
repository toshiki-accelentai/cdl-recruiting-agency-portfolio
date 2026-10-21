# Work plan

## Production-grade + learning track (started 2026-09-21)

Coach's brief: Python API → SQL database → CRM, with duplicate / missing-info /
failed-API handling and a "CRM is down, no lead lost" demo; then a recruiter
dashboard. Every step ships a learning doc. Index and progress checklist:
`docs/learning/README.md`. Full plan: Phase 0 → U (understand existing) → A
(receive + store, Postgres on Supabase) → B (outbox worker, resilience) → C
(dashboard). All data fictional; own VAPI + Zoho accounts only.

## Ship schedule — publish by 2026-10-31 (set 2026-10-11)

Budget: 2–3 h/day on the project. 10/23 was considered and dropped: no slack
left for understanding while building. **The publish date does not move; scope
is cut instead** (cut lines below). Every session also runs the 15-minute
learning routine in `docs/learning/README.md` → "Session routine".

- [ ] **10/12 (Mon, Canadian Thanksgiving — no test calls; booking rejects holidays)**
      Plan mode: B3 remaining scope (in / out). Draft the README skeleton.
- [ ] **10/12–10/18 — B3 done.** Finish step (4) shared-secret header (in progress,
      uncommitted on `feat/python-api`) and step (5) deploy + one real call + read the
      new log lines. Minimal alert when outbox rows stay `pending` too long or go
      `failed`. Out of scope: a monitoring stack, DNS changes (flake not reproducible).
- [ ] **10/19–10/25 — C done.** Read-only, NOT public (local or shown only on camera,
      so no auth work): recent calls, outbox status, Zoho sync result.
- [ ] **10/26–10/29 — Recording + write-up.** Record the B2 drill (+ dashboard).
      README + case study in this order: business problem and outcome → n8n/VAPI
      design → why Python was added for reliability. Known gaps listed honestly.
- [ ] **10/30–10/31 — Pre-publish check → publish.** No secrets, connection strings or
      the server IP in files or git history; test data (names, phones) fictional or
      anonymized; "Known issues" section matches reality; someone else can run the
      tests from the README. Then start applying.

**Cut lines (decide on the date, don't drift):**
- B3 not done by 10/18 → C becomes `scripts/outbox_status.py` output + Supabase
  table view instead of a new screen.
- C not done by 10/25 → record the drill only; show the dashboard as screenshots.
- Gaps that don't affect the demo (Callback note to Zoho, generated-suite drift,
  n8n `phone=` search) go in "Known issues", not into this month's work.

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
- [x] **B1** (done 2026-10-08, open finding: duplicate Zoho candidates, see below) Zoho client + outbox worker: DB row first, CRM sync after.
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
      **2026-10-08: step (5) DONE and verified.** 1 real VAPI web call (Test Driver Alpha,
      +1 206 555 0142). Supabase: 1 applicant, 1 call (callback 2026-10-09 17:00 UTC = 10:00
      Vancouver), outbox row `sent` on attempt 1, `zoho_candidate_id` written back. n8n Intake
      exec 9254 + Booking exec 9255 success; calendar event `cdlslot1lci7cg` created. n8n CDL 02+03
      set back to inactive (verified).
      **FINDING (decide before B2): two Zoho candidates for one call.** n8n's own Zoho branch
      (`…678001`, 17:01:34, Intake + Callback notes) and the worker (`…679001`, 17:01:35, Intake
      note) wrote 1s apart and did not see each other (n8n search uses the broken `phone=`).
      Options: (A) fix the n8n search to `criteria` (a 1s race may remain), (B) worker is the only
      Zoho writer and n8n keeps booking only (the intended design: DB first, CRM after).
      Test data left in place on purpose (both candidates, Supabase rows) as before/after evidence;
      the calendar event is deleted by hand in Google Calendar (the delete script only accepts
      `vapitest…` ids). Use a different fictional phone for B2.
      **FIXED 2026-10-08 (database-first Intake):** the worker is now the ONLY Zoho writer.
      `make_database_first` (scripts/build_modular_workflows.py, tested + mutation-checked)
      applied to the LIVE Intake by `scripts/deploy_intake_database_first.py` (dry-run default;
      18 -> 9 nodes; removed the 9 Zoho-writing nodes; live Intake rollback copy was kept only in
      the session scratchpad). Re-test: 1 real VAPI web call (Test Driver Bravo) -> Supabase call 3,
      outbox `sent` attempt 1, ONE Zoho candidate (`…679006`) + 1 Intake note, calendar event
      created, n8n Intake exec 9257 ran only the 9 remaining nodes. n8n CDL 01-04 inactive again.
      Side effects of the session: a manual "Execute workflow" in the n8n editor replays the
      last webhook data and DOES run side-effect nodes (inactive != safe): it saved John Smith
      (A3 payload) as Supabase call 2 and added 1 duplicate Intake note to the existing Zoho
      candidate `…599016` (phone dedupe worked: no new candidate).
      **Gap (b) FIXED 2026-10-09 (not yet exercised live):** the caller used to be told "saved"
      without waiting for the `Save to Database API` result (side branch, onError=continue), so a
      failed save lost the lead silently. `require_database_save` (tested, 4 mutations caught) +
      `scripts/deploy_intake_require_db_save.py` added `Saved to Database?` (reads the save's
      `call_id`) and `Respond Save Failure` (saved:false, manual_followup) to the live Intake
      (11 nodes, inactive). STILL TO DO: one happy-path call (booking must still work) and one
      call with the API stopped (expect `Respond Save Failure`); then start the API again.
      **STATE AT END OF 2026-10-08 SESSION (read first tomorrow):**
      - Call A (happy path, Test Driver Charlie) PASSED with the new `Saved to Database?` node.
      - Call B (API stopped) 1st try: n8n behaved correctly (exec 9261: Save timed out ->
        `Respond Save Failure`), but the AI SAID "details saved". Root cause = VAPI prompt line
        "I've got your details saved…" in `config/vapi/prompts/*.md` step 4 (not the backend).
      - FIXED live: both assistants' system prompt now branches on `status`/`saved` (new-lead +
        existing-lead), pushed with `scripts/deploy_vapi_prompt_only.py` (prompt text only; model
        untouched). Pre-change copies in the session scratchpad only. UNCOMMITTED: the two prompt
        files, `deploy_vapi_prompt_only.py`, this note.
      - **LIVE STATE LEFT BEHIND:** the API container `cdl-api-cdl-api-1` is STOPPED for the next
        test (worker still up). Restart: `ssh -i ~/.ssh/hermes-hetzner hermesadmin@62.238.51.45
        "sudo -n docker start cdl-api-cdl-api-1"`. n8n CDL 02 + 03 are ACTIVE on purpose (user
        decision 2026-10-08: it is a demo, stay published). While the API is down, any call will
        hit the save-failure path.
      - **2026-10-09 RESULT (call B PASSED):** VAPI live calls use the last PUBLISHED assistant
        version, not the newest version: `PATCH /assistant` only creates a version (v8, v10 never
        reached calls); Publish is dashboard-only (no publish API documented). A stale dashboard
        draft that was published/saved overwrote my change once (new-lead v9). Fix: user replaced
        the "4. Book it" block in the dashboard and published v11. Test Driver Foxtrot call with
        the API stopped: n8n `Respond Save Failure`, AI said "I'm sorry… couldn't save your details,
        please call back" (no "saved", no "booked"). Real-action count for 2026-10-09: 3 VAPI web
        calls (19:38 Echo on a stale prompt, 19:46 Foxtrot on the published old version, 19:53
        Foxtrot on v11), 0 Zoho/Supabase/calendar writes from them (API was stopped).
        Live v11 for new-lead lacks the closing line `**Never say a call is scheduled until the
        tool has confirmed it.**` (the user dropped it while pasting; the block's first paragraph
        covers the same rule). `existing-lead` prompt NOT yet published (its PATCHed version is not
        what calls use); do the same dashboard replace + Publish there. Workflow from now on:
        edit `config/vapi/prompts/*.md` -> `deploy_vapi_prompt_only.py` -> reload dashboard,
        verify text, Publish. Calendar events from this session's tests: delete by hand.
      - (superseded by the result above) NEXT: (1) re-run call B with the API still stopped (Test Driver Echo, 206 555 0146,
        tomorrow 3 PM) and listen for: no "booked/locked in" before the result, "couldn't save,
        please call back", never "saved"; verify via n8n exec + VAPI call transcript; (2) restart
        the API and confirm healthy; (3) align the n8n `Respond Save Failure` message with the
        prompt ("recruiter will follow up" is untrue when nothing was saved); (4) drift:
        live VAPI model is `gpt-5` but `config/vapi/desired.json` says gpt-4.1/0.3 (do NOT run
        `deploy_vapi.py --apply` until reconciled; ask which is intended, then
        `python scripts/export_config.py`); (5) commit; (6) B2.
      **Known gaps (do before B2):** (a) the Callback note (booking outcome) is no
      longer written to Zoho: route it through the API/outbox if wanted; (c) the generated suite
      `config/n8n/production/modular/` still has the old Zoho-writing Intake (live differs).
      Test leftovers kept on purpose: Zoho candidates Alpha x2 / Bravo x1 / John Smith note,
      Supabase 3 calls; delete the 2 calendar events by hand (Alpha 10/9 10:00, Bravo 10/9 11:00).
      **FINDING (B3):** the VPS resolver intermittently fails to resolve the Supabase host
      (worker logged ~12 `database unavailable: failed to resolve host` blips on 2026-10-08, all
      auto-recovered; one happened right before the test call). If it hits while the API handles
      `POST /calls`, that call's save fails. Look at DNS (systemd-resolved) / retry in the API.
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
- [x] **B2** "CRM is down" drill DONE 2026-10-09 (not recorded; runbook in
      `docs/B2-CRM-DOWN-DRILL.md`, status board `scripts/outbox_status.py`, read-only).
      Broke Zoho by appending `ZOHO_RECRUIT_API_DOMAIN=https://zoho-down.invalid` to the server
      `.env` + recreating the worker; removed it and recreated again to restore (a restart alone
      does not reload env). 2 real VAPI web calls while down (Drill Wang …0151, Joel Michael
      …0152): both saved to Supabase, AI told them "saved/booked", outbox `pending` with attempts
      rising (30/60/120/240s backoff), 0 Zoho writes. After restore both went `sent` on their own
      (Joel after 5 tries, Drill Wang after 6, ~7 min backoff wait), 1 Zoho candidate + 1 note
      each, no duplicates; final: calls 6 = sent 6, pending 0, failed 0. The server `.env` is
      back to 4 keys. Real actions: 2 VAPI calls, 2 Zoho candidates + 2 notes (via the worker).
      Leftovers: delete the 2 drill calendar events by hand.
- [ ] **Record the B2 demo** (headline interview demo): redo the runbook on camera after C/B3,
      ideally with the dashboard showing leads while Zoho is down.
- [x] **B3** (done 2026-10-12) Logging/observability + deploy + API key (VPS DNS flake: retry added, root cause not found, see FINDING (B3) above).
      **2026-10-10 progress:** (1) DNS flake could NOT be reproduced
      (120 lookups in the worker container + 160 direct to the 4 Hetzner resolvers: 0 failures; old
      logs gone after the B2 recreate), so no server DNS change. (2) `app/db.py connect_with_retry`:
      3 tries (0.5s, 1s waits), only for `OperationalError`; used by `POST /calls`. (3) Logging:
      `app/logs.py`; API logs call saved / duplicate / save failed + each failed connect try (ids
      only, no phone or name); worker logs row id, attempt, next wait, after the commit; errors cut
      to 150 chars. 88 tests green on local Docker Postgres, 9 new log tests + 4 retry tests,
      mutation-checked. Removed an empty accidental `api/.git`.
      **2026-10-12 steps (4) + (5) DONE and verified.** (4) `POST /calls` needs header `X-API-Key`
      (401 wrong/missing, 503 if no secret configured, `/docs` open for the healthcheck); key in
      n8n Header Auth credential `CDL API key` (id `QCHUta63QD70Ahf1`, created by hand in the UI),
      live Intake node `Save to Database API` patched by `scripts/deploy_api_key_auth.py` (only
      that node changed; rollback copy of the old Intake was kept only in the session scratchpad).
      Secret: local `api/deploy/.env.api` (git-ignored) and `/opt/cdl-api/.env.api` (chmod 600,
      read only by the API container, NOT the worker). 97 API tests + 38 unittest, mutation-checked.
      (5) Deployed with `scripts/deploy_api_to_vps.ps1` (run by the user; rollback copies
      `compose.yaml.before-20261010-162540`, `src.before-20261010-162540` on the server). In-container
      check: no key 401, wrong key 401, right key + `{}` 422. Real test call (Test Driver, ...0160):
      API log `call saved call_id=7` / `POST /calls 201` from n8n, outbox `sent` attempt 1, Zoho
      candidate `...688001`. Real actions: 1 VAPI web call, 1 Zoho candidate + 1 note (worker), 1
      calendar event (not inspected; delete by hand). Not done: VPS DNS flake has no fix (could not
      reproduce); the generated suite `config/n8n/production/modular/` does not have the key auth
      (credential ids are instance-local), so never redeploy it over the live Intake.
- [ ] **C** Recruiter dashboard (review summaries, correct info, track
      follow-ups). No longer waits for the recording.
      **Scope decided 2026-10-12 (supersedes the "read-only, not public" line in the ship
      schedule):** production-level, public with login, demo credentials on the resume.
      Reason: the goal is a real system, not a demo; the mentor's brief is review / correct /
      follow-up, which needs writes. Design:
      - FastAPI serves the HTML itself (no separate frontend); everything through the Python API;
        a correction writes to Postgres and queues an outbox row so the worker updates Zoho.
      - Auth with two roles: `recruiter` (demo login on the resume: review, correct, follow-up,
        no delete) and `admin` (owner only, never published). Hashed passwords, expiring sessions,
        rotatable demo password.
      - Safe for strangers: rate limit, field length limits, audit log (who changed what), nightly
        reset of the fictional data from a seed. Only fictional data exists in these accounts.
      - Public via the existing Caddy on hermes-vps (add a `dashboard.` host block pointing at
        `cdl-api:8000`; needs a DNS record + Caddy on the same Docker network as `cdl-api`).
        Close `/docs` and keep `POST /calls` unreachable from outside before going public.
        Cloudflare Tunnel is the fallback if Caddy can't be used. Zoho-down drill stays admin-only
        (recording), never a visitor toggle.
      - Pending-row screen (learner's prediction, corrected): the call IS saved in Postgres; only
        the Zoho sync is waiting. Show "saved, waiting for Zoho", attempts, next retry, last error,
        and "urgent: register manually in Zoho with the same phone" (worker dedupes by phone).
      - Known gap: no `summary` column (only `raw_payload` + Zoho notes); a later migration, listed
        under Known issues if not done.
      Order: C1 API read + correct + follow-up endpoints and auth (test-first) → C2 HTML pages →
      C3 Caddy/DNS publish, `/docs` closed → C4 rate limit, audit log, nightly reset, rotate demo
      password. **Cut line (10/25):** if auth + list/edit is not live, ship without follow-up
      tracking and show the rest as screenshots.
      **STATUS 2026-10-14 (end of session): C1 backend DONE, all committed on `feat/python-api`,
      187 API tests green (needs Docker Desktop running; start `api-db-1`), NOT deployed.**
      C1a login `f1e4c0c`; C1b list/detail `abaed40`; C1c worker uses stored Zoho id `deb7688`,
      fallback `e547de6`, corrections endpoint `3cf2778`, worker sends corrections `b5b9661`;
      C1d follow-up status + `new_call_since` marker `eb9262e`. Migrations 007-010 exist locally
      only; they reach Supabase when the API container starts after a deploy (user runs
      `scripts/deploy_api_to_vps.ps1`; API + worker must deploy together). Still to do for a
      real run: one live Zoho smoke test of a correction (writes to the sandbox Zoho; user decides),
      create the demo + admin users with a script (not written yet; passwords never in chat/git).
      Three debug drills done (flipped name check, NULL in the worker query, `session_version = 1`);
      notes in `docs/learning/interview-story.md`.
      **NEXT: C2 (HTML pages served by FastAPI).** Decided 2026-10-15: first screen = (B) a
      "To do" list, one row per PERSON (needs-review calls, Zoho sync failed, `to_call`, "called
      again" marker; problems first, then HOT→COLD, then earliest callback), full calls table
      behind a tab. Pages: Login → To do → All calls → Applicant detail (fields | call history +
      transcript + audio | follow-up, note, change history, Zoho sync). Light, calm theme; rows on
      desktop, cards on phone. Dropped (no data): CDL class/endorsements, pipeline stages (Zoho
      owns them), live calls, agent-quality metrics, SMS/scheduling. Backend gap: `/api/calls` is
      one row per call; the To do list needs a per-applicant read endpoint. Design skills to
      consider: `design-taste-frontend`, `minimalist-ui`. Order: C2 To do page → C1e → rest of
      C2. Then C3 (Caddy + DNS, close `/docs`) and C4 (rate limit, nightly reset, rotate demo
      password).
      **C1e Call transcript, summary and audio on the applicant page (added 2026-10-15).**
      Clients expect to hear the call without logging in to VAPI. Both assistants already send
      `end-of-call-report` to the n8n post-call webhook; the Python API ignores it today.
      - New API receiver for the end-of-call report: match on `vapi_call_id`, store `transcript`
        and `summary` (closes the "no summary column" gap). A report with no matching call row
        (non-driver, off-script, or hung up before `logApplicantInfo`) is saved as a
        needs-review call, never dropped (A2 rule). Wire it via `server.url` or an n8n forward:
        a live config change, needs approval.
      - Audio: VAPI's stored `recordingUrl` is a private bucket (no-login fetch → 400). Checked
        2026-10-15, read-only: `GET /call/{id}/mono-recording` with the private key → 302 to a
        signed link valid 30 min (`X-Amz-Expires=1800`), plays without login (206, audio/wav).
        So: store only the VAPI call id; a logged-in `GET /api/calls/{id}/recording` asks VAPI
        and redirects to a fresh link. Key stays on the server; never store the signed link.
      - Recording notice added to both `firstMessage`s in `config/vapi/desired.json`
        (2026-10-15). **NOT deployed**; deploy with explicit approval, then re-export and confirm
        a test call speaks it.
      - Schedule risk before the 10/25 cut line: if short on time, cut audio, keep the queue.
      **STATUS 2026-10-16: C1e code DONE and committed (`f7a5257`, `cec07dd`, UI commit after), 277 API
      tests, NOT deployed, no live change made.** C1f caller ID `4c8514f`; To do endpoint + pages
      `a8b8b22`, `4ba0d68`; Applicant detail endpoint + page `404fec8`, `90a63b0`. Checked in a browser against
      two real VAPI calls (read-only GETs): signed link plays, click on a transcript line seeks.
      **DEPLOYED 2026-10-16 17:59 Vancouver (approved by the owner): API + worker on hermes-vps, migrations 007 to
      012 applied to Supabase (checked read-only: 7 applicants, 7 calls, 7 outbox rows unchanged; `users` and
      `audit_log` exist and are empty).** Real actions: 1 deploy script run (about 8 SSH sessions, 3 scp, 2 container
      rebuilds), 6 migrations, 0 phone calls, 0 Zoho writes. Checked from inside the container: 11 of 11 (key auth
      401/401/422, login 401 for an unknown user, pages 200, dashboard endpoints 401 without a login). Rollback copies:
      `compose.yaml.before-20261016-175927`, `src.before-20261016-175927` in /opt/cdl-api. `.env.api` on the server now
      has API_SHARED_SECRET, SESSION_SECRET, VAPI_PRIVATE_KEY. The deploy script's last check had a PowerShell BOM bug,
      fixed (cmd /c type). The dashboard is NOT reachable from outside yet (no published port: C3), and there are 0 users.
      **LOGINS CREATED 2026-10-17 (approved):** `demo` (recruiter) and `owner` (admin) in Supabase via `users_cli`; the
      passwords are in `C:\Users\gdeta\cdl-passwords\` (outside the repo; move owner's into a password manager, then delete
      the file). Checked inside the server container: both log in (200), `/api/me` and `/api/todo` work with the session
      (200, 7 rows to call back from the 7 test applicants), a wrong password gives 401. Real actions: 2 inserts into
      `users`, 2 ssh sessions, 0 calls, 0 Zoho writes. NOT verified: a real browser against the live server (needs C3),
      HTTPS and the Secure cookie, audio playback of a real recording on the server, the n8n to /call-reports hop.
      Auth is going public in C3: get an independent review of login, cookie and rate-limit settings before DNS goes live.
      **Still waiting for approval (steps 1 and 2 below are done):**
      1. Server `.env.api` on hermes-vps: add `VAPI_PRIVATE_KEY` (the recording endpoint needs it; the key stays
         in the API container only). Tradeoff: it is VAPI's full-power private key, there is no read-only key.
      2. Deploy API + worker together with `scripts/deploy_api_to_vps.ps1` (migrations 007 to 012 run on start;
         they reach Supabase). Then re-export live config and diff.
      3. n8n: add a node on the post-call webhook that POSTs the end-of-call report to `http://cdl-api:8000/call-reports`
         with the X-API-Key header (same as "Save to Database API"). Do NOT redeploy the generated modular suite.
      4. VAPI: the recording notice in `config/vapi/desired.json` firstMessages (committed, not deployed).
      5. Create the logins with `api/app/users_cli.py` (written, tested; passwords go to an owner-only `*.password` file,
         never printed, git-ignored). After step 2 (migration 007 creates the `users` table), from the repo root:
         `cd api; .venv\Scripts\python.exe -m app.users_cli create demo recruiter --write-password-to ..\demo.password --env-file deploy\.env.supabase`
         and the same with `owner admin`. `rotate` and `list` exist too. This is a LIVE write to Supabase: ask first. Then one real phone call:
         check the call row, summary, transcript, audio, and that `message.call.customer.number` arrives.
      Assumptions to verify on that first real call: the report webhook carries `analysis.summary`,
      `artifact.messages` and `artifact.recordingUrl` (the code also accepts the older top-level fields).
      Not built yet: All calls page; Zoho "Open in Zoho" link (no org URL known); worker note does not yet
      include `callback_phone`; Caddy/DNS (C3); rate limit and nightly reset (C4).
      **Teaching style for this owner (in CLAUDE.md):** plain words + the real term, one small
      chunk then one check question, glossary entry per new term.
      **Uncommitted docs:** CLAUDE.md, glossary.md, learning README, interview-story.md, this file.
      **C3 PLAN written 2026-10-17, NOT executed: `docs/C3-PLAN.md`.** Caddy already runs (`n8n-caddy-1`, same network as
      `cdl-api`), DNS is at Cloudflare. Needs from the owner: the hostname (recommended `cdl-demo.accelentai.com`), the
      order (recommended: code hardening and login throttle first), and a decision that the 7 test applicants are replaced
      by fictional seed data before the link goes on a resume.
      **SPEED FIX B + STATIC CACHE DEPLOYED 2026-10-19 17:57 Vancouver (approved by the owner), code `0b13733`.** Rollback copies:
      `src.before-20261019-175652`, `compose.yaml.before-20261019-175652` (compose unchanged). Verified: in the live container
      19 of 19 checks, both logins 200 (wrong password 401), outside 26 of 26, fingerprinted URLs `public, max-age=31536000,
      immutable`, plain URLs `no-cache` with 304 on ETag, no errors in the API logs. Real actions: 1 deploy script run, 0
      migrations, 0 phone calls, 0 Zoho writes. Owner's browser check: faster, rows close smoothly.
      **BACKFILL DONE 2026-10-19 (approved by the owner):** the 7 existing calls got summary, transcript and the recording flag.
      Real actions: 7 VAPI `GET /call/{id}` (read), 7 `POST /call-reports` from inside the container (each updates one existing
      `calls` row), 0 new rows, 0 outbox rows, 0 Zoho writes, 0 phone calls. Checked read-only afterwards: 7 of 7 calls now have
      summary + transcript + recording flag; row counts unchanged (applicants 7, calls 7, outbox 7, users 2). To undo: set
      `summary`, `transcript`, `caller_number`, `report_received_at` to NULL and `has_recording` to false on those 7 rows.
      **N8N HOP DONE 2026-10-20 (the owner did the n8n edit by hand, guided):** new node `Save Report to Database API` in the live
      `CDL 04 - Post-Call Report` (n8n.accelentai.com, id XGMOFG1hROutdkCF): POST `http://cdl-api:8000/call-reports`, Header Auth
      credential `CDL API key`, body = the VAPI report, 3 tries, 2000 ms wait, 10 s timeout, a side branch off `Acknowledge Post Call`.
      Gotcha: in this n8n, Save only stores a draft; the owner had to press Publish (the first test call, id 8, missed the hop and
      has no summary/transcript yet). Verified with a real call (id 9, 23:18 UTC): API log `POST /call-reports 200` from the n8n
      container, row 9 has summary + transcript + recording flag, outbox sent. Real actions: 2 phone calls (owner), usual test writes
      to the owner's Zoho/Calendar, 0 Claude writes. Open: call 8 can be backfilled with the same container script.
      **SPEED FIX B + STATIC CACHE built 2026-10-20, committed (now deployed, see above).** The owner still felt it slow and the row removal
      clunky. Cause: after a click nothing moved until the save returned (about 0.4 s), then the row faded but kept its height, then
      the whole list was rebuilt (everything jumped). Now (`api/app/static/todo.js`, `app.css`): the row closes smoothly at once
      (height, padding, opacity 200 to 260 ms), the number changes in the first frame, the save runs in the background, a failed
      save brings the row back in place, Undo is instant, and no full reload. A refresh that started before a change is dropped
      (that race showed the count as 7 for a moment; fixed and checked). Found on the way: static files had no cache headers, so a
      browser kept an OLD app.css after a deploy; pages now link `/static/x?v=<fingerprint>` (`api/app/pages.py`), cached for a
      year, and a changed file gets a new URL. 356 API tests. Checked in a real local browser (no way to measure frame rates when the
      pane is not visible): transitions start at the click, stale refresh dropped, failure and undo OK. NOT done: the detail page
      still reloads everything after a follow-up change; the first page load still needs HTML, then the data (two round trips).
      **SPEED FIX A DEPLOYED 2026-10-19 17:32 Vancouver (approved by the owner), code `bfe304c`.** Rollback copies:
      `src.before-20261019-173220`, `compose.yaml.before-20261019-173220` (compose unchanged). Verified: in the live container
      19 of 19 checks, both logins 200, outside 26 of 26, no pool warnings or errors in the API and worker logs (only the expected
      warnings from the deliberate wrong-password tests). Speed measured in the container, same script as before: To do handler
      361 ms -> 199 ms, applicant handler 367 ms -> 199 ms (the first call after a start is about 400 ms because it opens the first
      connection). Server-side per dashboard request about 640 ms -> about 260 ms; adding the 170 ms Vancouver to Helsinki distance
      the page request should be about 430 ms (calculated, not measured end to end: that needs a signed-in browser). Real actions:
      1 deploy (about 8 SSH sessions, 3 scp, 2 rebuilds), 0 migrations, 0 phone calls, 0 Zoho writes. Open: the owner's felt speed,
      optional speed fix B (instant feedback in the page).
      **SPEED FIX A (connection pool) built 2026-10-19, committed, NOT deployed.** Why: every request opened new database
      connections (about 250 ms each, two per request: sign-in check + the work). Now `api/app/db.py` lends out 1 to 4 open
      connections (`psycopg-pool`, approved by the owner), all 11 request-path call sites use `db_connection()`; the CLI and the
      worker are unchanged. Measured inside the live container (read-only): server-side time per dashboard request
      639 ms -> 264 ms (2.4x). Expected for the user: about 810 ms -> 430 ms per page load (the 170 ms Vancouver to Helsinki
      distance stays). 343 API tests, 3 mutation checks plus 2 more, local browser check OK. To go live: deploy (the rebuild installs
      `psycopg-pool`), then re-measure in the container. Optional later: speed fix B (instant feedback in the page), the pool's
      per-borrow check costs one 29 ms round trip (about 22 percent of the 264 ms).
- [ ] **n8n workflow review (owner does this themself; added 2026-10-19 as a reminder).** Go through the n8n
      workflows by hand (the real ones on `accelentai.app.n8n.cloud`, not the inactive copy) and check them against
      `config/n8n/`: which node sends the end-of-call report (it must reach `POST /call-reports`), the `toolCalls[0]`
      vs `toolCallList[0]` mix, the Zoho `Authorization` header (AUDIT #6), and that nothing still writes to Airtable
      that should not. Do before the independent security review and before the link goes on a resume.
- [ ] **C4 demo server (decided 2026-10-20, plan in `docs/C4-PLAN.md`).** Separate demo container + Postgres on
      hermes-vps, fictional seed, nightly reset, one or two sample recordings, no Zoho/VAPI keys. First-pass review in
      `docs/SECURITY-REVIEW.md`: do not share the demo password before this is live.
      **STATUS 2026-10-21:** Part A step 1 DONE (`edcbbb8`, tests that the server runs with no n8n/VAPI key) and step 2
      DONE (`9dd4a42`, `app/demo_seed.py`, guarded by `DEMO_MODE=1` + empty DB; never run against any real DB, only the
      test DB). Full suite 377 passed. **NEXT: step 2b sample recordings, step 3 nightly reset `app.demo_reset`
      (same guards), step 5 SECURITY-REVIEW findings 3-5, then Part B independent review, then the live steps (each
      needs approval).** UI files under `api/app/static/` are being changed in Codex: do not touch or commit them.
      Run tests with `api/.venv/Scripts/python.exe -m pytest` (needs Docker Desktop + `api-db-1`).
- [ ] **Apply.**
- [ ] **Public demo phone line (after publish, only if time allows; decided 2026-10-20).** Visitors call a demo
      agent and see their call appear on the demo dashboard. Demo server only, no Zoho; call length cap, recorded-call
      notice, masked phones; costs a number plus per-minute fees.
- [ ] **Interview-prep code review (last item, after publish and first applications; added
      2026-10-13).** One or more sessions to read and understand the finished portfolio code
      well enough to defend it in an interview. Per area: walk the data flow out loud without
      notes, answer "why this design, what did you reject", then plant or find one bug and
      debug it alone. Areas: intake path (`POST /calls`, dedupe, `needs_review`), outbox +
      worker (retry/backoff, stored Zoho id + fallback), auth (`session_version`, roles),
      corrections (409 on a taken phone, audit log), the CRM-down drill, the test suite
      (what each mutation check proves). Output: finish `docs/learning/interview-story.md`
      and a one-page "known gaps" list I can state honestly. Deadline: before the first
      interview, not before publish; it never blocks the 10/31 publish date.
- Deferred until after applying: U9 checkpoint, deep walkthroughs, concept
  checks (these are folded into the interview-prep review above).

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
