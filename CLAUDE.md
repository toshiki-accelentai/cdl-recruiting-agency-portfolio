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

## API tests: one pytest at a time (every session, every tool)

The API tests share ONE test database (`cdl_test` on `api-db-1`), and each pytest session DROPS and recreates it.
A second pytest running at the same time kills the first one's connections, and both report failures that are not
real bugs (this gave a fake "52 failed, 25 errors" on 2026-10-21).

**Before running pytest, check that no other pytest is running. Run it through the guard:**

```bash
py -3.11 scripts/run_api_tests.py                       # whole suite; refuses if another pytest is alive
py -3.11 scripts/run_api_tests.py tests/test_worker.py -q
```

If it prints "Another pytest is already running", wait for that process (it shows the pid) and retry. Never
start a second run, and never trust a red result from a run that overlapped another one: re-run it alone first.
Needs Docker Desktop and the `api-db-1` container running.

## Two sessions in one working tree: commit and deploy rules

Claude (or Codex) may run in a second session on the same checkout, for example while the n8n code nodes are
being fixed here and the matching API parsing is fixed there. Editing and committing in parallel is fine if:

- **Commit only your own files**, by name: `git add path/to/file ...`. Never `git add -A`, `git add .` or
  `git commit -a`: that would sweep in the other session's half-finished edits.
- **Never run the API deploy script while either session has uncommitted changes.** `scripts/deploy_api_to_vps.ps1`
  packages the whole `api/app` folder from the working tree, so it would ship the other session's unfinished work.
  Deploy from a clean release worktree (a separate checkout of exactly the commit being released), never from the
  shared working tree. The release is checked first: live source vs git, full tests, a list of the files that change.
- **n8n and API changes that depend on each other go live together, as one approved step** (for example n8n
  code-node parsing and the matching API parsing). Do not deploy one side alone and leave the other behind.
- Every deploy, VAPI patch or n8n publish needs the owner's explicit approval first; report real actions
  separately from test counts.
- Run the API tests only through `scripts/run_api_tests.py` (see the section above).

## Learning routine

The owner is learning through this project (publish target 2026-10-31, schedule in
`tasks/todo.md`). Each session follows `docs/learning/README.md` → "Session routine":
ask for a one-line prediction before implementing, let the owner write state-check SQL
first, and end by prompting a 3-line entry in `docs/learning/build-notes.md`
(the owner writes it; Claude only fact-checks).

## Learning and verification

- Do not ask me to judge technical correctness by reading code alone. Help me define the desired user outcome in plain language.
- For each significant change, recommend an approach and explain the expected behavior, important failure cases, and reasons for the choice.
- After implementation, report the expected result, the observed result from tests and the actual UI/API/database/integration, and what remains unverified. A passing AI-written test alone is not enough.
- For public access, authentication, data writes, and external integrations, check relevant primary documentation and recommend independent review when important uncertainty remains.
- Teach one small concept from the real code at a time. Invite a short prediction, then show the evidence. Keep the current dashboard moving; reserve deeper study for a few critical paths.
- Keep the current delivery priority. Do not pause dashboard work to reverse-engineer the entire repository or require line-by-line mastery first.
- The owner decides the user outcome, business rules, constraints, and acceptance criteria. Claude may propose designs and implement bounded changes.
- After each meaningful change, briefly explain what changed, why, the main code path (with file and line references), and how it was verified. State what the owner decided and what Claude generated; never imply the owner authored AI-generated code.
- When debugging as a learning exercise, show the expected and observed behavior and point to the relevant test or code. Invite the owner's hypothesis before giving a hint when practical. If the owner asks for a direct fix, make the fix and explain it briefly afterward.
- Build interview readiness by helping the owner explain and verify a few critical paths: deterministic booking or temperature rules, API-to-database-to-CRM handling, and a recruiter dashboard flow. Do not require memorizing every line or dependency.
- Keep interview notes factual: distinguish the original workflow and its real results from the portfolio rebuild, and distinguish owner decisions from AI implementation.

## How to talk to the owner (plain words, real vocabulary)

The owner is not an experienced developer yet and must also learn the technical words for
interviews. Never make them ask for a simpler version.

- Plain words first: say what a thing does in everyday language, with a short real-life
  comparison when it helps (front desk, courier, delivery slip).
- Keep the real term, once, next to the plain explanation, e.g. "the delivery slip (the
  **outbox row**)". Never drop the term, never leave it unexplained.
- At most one new term per sentence, defined in that same sentence. Do not stack jargon.
- Every new term goes into `docs/learning/glossary.md` (one plain sentence; "First seen" = chunk).
- End each chunk with **Words to learn today**: 3 to 5 terms, each with a one-line plain meaning.
- Short sentences. Numbers and file names only when they help the owner act.
- One small chunk at a time: explain ONE idea (a few lines), then ask one quick check question and
  stop. Give the next chunk only after the owner answers and has understood. Never dump a full
  walkthrough, and do not stack extra "words to learn" lists until the chunk is understood.
- English by default; Japanese when the owner asks.

## Safety

Deploys to VAPI or n8n change a system that answers real phone calls. Treat any
`PUT`/`PATCH`/`POST` to those APIs as a live side effect: get explicit approval,
and report real-call counts separately from dry runs.
