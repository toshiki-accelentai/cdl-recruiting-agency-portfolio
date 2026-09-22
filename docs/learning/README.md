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

## Progress

### Phase U: Understand what exists
- [ ] U1 [One call, end to end](existing/01-end-to-end-call-trace.md)
- [ ] U2 [n8n basics: Routing and Post-Call](existing/02-n8n-basics-routing-and-post-call.md)
- [ ] U3 Applicant Intake (17 nodes): error paths, sub-workflow
- [ ] U4 Calendar Booking: idempotency, race conditions
- [ ] U5 `cdl_helpers.js`: the business logic, read side by side with Python
- [ ] U6 How the Python scripts call APIs (`export_config.py`, `deploy_vapi_tool.py`)
- [ ] U7 Workflows-as-code and the test suite
- [ ] U8 Smoke tests and live-side-effect scripts
- [ ] U9 Checkpoint: explain it back, plus a debugging drill

Running list: [improvements.md](existing/improvements.md)

### Phase A: Receive and store
- [ ] 1 Python project skeleton
- [ ] 2a SQL from zero · [ ] 2b Practice queries · [ ] 2c JOINs
- [ ] 3 Migrations · [ ] 4 Webhook endpoint · [ ] 5 Transactions · [ ] 6 Duplicates and missing info

### Phase B: CRM sync and resilience
- [ ] 7 Zoho client · [ ] 8 Outbox worker · [ ] 9 "CRM is down" drill · [ ] 10 Observability · [ ] 11 Deploy

### Phase C: Recruiter dashboard
- [ ] 12–14 (planned when Phase B is done)

## Reference
- [glossary.md](glossary.md): every term, one line each
- `interview-story.md`: STAR narrative (starts at the end of Phase U)
