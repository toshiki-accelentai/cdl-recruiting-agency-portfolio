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
- [ ] A3 Applicant Intake points at the API; real test call verified in the DB

### Phase B: CRM sync and resilience
- [ ] B1 Zoho client + outbox worker
- [ ] B2 "CRM is down" drill, **recorded as the interview demo**
- [ ] B3 Observability + deploy

### Phase C: Recruiter dashboard
- [ ] C (planned once B2 is recorded)

### Then: apply

## Reference
- [glossary.md](glossary.md): every term, one line each
- `interview-story.md`: STAR narrative (starts at the end of Phase U)
