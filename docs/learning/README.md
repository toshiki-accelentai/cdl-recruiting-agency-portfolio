# Learning track

This project doubles as my Python + SQL + automation-engineering curriculum.
Every step ships with a doc I can study before an interview. Full plan:
`tasks/todo.md` → "Production-grade + learning track".

## How each step works

1. Claude Code implements (test-first) or, in Phase U, explains existing code.
2. I read the doc, then **run it myself**.
3. I do the **Break it & fix it** exercise without help first.
4. I answer the interview questions out loud, then compare with the model answers.
5. Only then does the box below get ticked.

Doc template: Goal · Why it matters · Concepts · Walkthrough (file:line) ·
Try it yourself · Break it & fix it · Interview Q&A · Glossary terms.

From U8 onward, the Q&A section splits in two, kept separate: **Interview
questions** (design-reasoning and how AI tools were directed/verified — not
code mechanics) and **Concept check** (plain Python/SQL/new-concept
comprehension questions, for learning the language itself, not interview
prep).

## Priority shift (2026-10-03)

Mentor's guidance: ~60% code understanding is enough for an AI Automation
Specialist role. **Ship the project and start applying first**; close
line-by-line study happens later, while waiting on interviews. From here,
Phase A/B docs are short: architecture, data flow, the CRM-outage demo, and
interview talking points. Deep walkthroughs are deferred.

## Session routine (from 2026-10-11, +15 min per work session)

Goal: be able to explain every piece of this project in my own words by the
2026-10-31 publish date, without slowing the build.

1. **Before starting — predict (1 line).** What will happen / how I'd fix it.
   Claude asks for this before implementing and waits for my answer.
2. **When checking state — write the SQL myself first.** Outbox, calls,
   applicants queries in Supabase; then compare with Claude's version.
3. **After finishing — explain back (3 lines)** in `interview-story.md`:
   what I did / why / the option I rejected.
4. **Name the Claude Code piece used** (subagent / hook / skill / MCP / plan
   mode) and why — or why none was needed. One line under the same entry.

Story bank already earned (write these up first, week of 10/12):
- Two Zoho candidates per call → the worker became the only Zoho writer.
- Caller heard "saved" when the save failed → branch on the save result,
  then the VAPI prompt had the same lie → fixed there too.
- VAPI `PATCH` doesn't reach live calls; only the published version does.
- Editing `.env` did nothing until the container was force-recreated.
- CRM-down drill: Zoho broken, 2 calls, 0 leads lost, both synced after restore.

## Progress

### Phase U: Understand what exists
- [x] U1 [One call, end to end](existing/01-end-to-end-call-trace.md)
- [x] U2 [n8n basics: Routing and Post-Call](existing/02-n8n-basics-routing-and-post-call.md) — **skipped 2026-09-25**: content (`retryOnFail`, `onError`, `$json` vs `$('Node')`) was already covered hands-on during U3/U4's live debugging.
- [x] U3 [Applicant Intake (17 nodes)](existing/03-applicant-intake.md): error paths, sub-workflow
- [x] U4 [Calendar Booking](existing/04-calendar-booking.md): idempotency, race conditions
- [x] U5 [`cdl_helpers.js`](existing/05-cdl-helpers.md): the business logic, read side by side with Python
- [x] U6 [How the Python scripts call APIs](existing/06-python-scripts-calling-apis.md) (`export_config.py`, `deploy_vapi_tool.py`)
- [x] U7 [Workflows-as-code and the test suite](existing/07-workflows-as-code-and-test-suite.md)
- [x] U8 [Smoke tests and live-side-effect scripts](existing/08-smoke-tests-and-live-side-effect-scripts.md)
- U9 Checkpoint: *deferred until after applying*

Running list: [improvements.md](existing/improvements.md)

From Phase A on, each chunk's doc is short: what it does · data flow · key
design decision · 2–3 interview talking points · **one debug drill** (solve
it alone first). SQL is explained inside the chunk that uses it.

### Phase A: Receive and store
- [x] A1 [Python API + Postgres](A1-api-and-postgres.md): receive an intake payload, save it in one transaction
- [x] A2 Duplicates and missing info: replay-safe, one applicant per phone, bad/missing info flagged not rejected (drill done: `drills/a2-planted-bug.patch`)
- [x] A3 Applicant Intake points at the API; real test call verified in the DB (done 2026-10-06)

### Phase B: CRM sync and resilience
- [ ] B1 Zoho client + outbox worker
- [x] B2 "CRM is down" drill (done 2026-10-09, runbook `docs/B2-CRM-DOWN-DRILL.md`;
      recording it is a separate final task)
- [ ] B3 Observability + deploy

### Phase C: Recruiter dashboard
- [ ] C (next)

### Then: apply

## Reference
- [glossary.md](glossary.md): every term, one line each
- `interview-story.md`: STAR narrative (starts at the end of Phase U)
