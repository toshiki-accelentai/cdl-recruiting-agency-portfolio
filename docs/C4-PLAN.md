# C4 plan: independent review, then a safe public demo (fictional data, nightly reset, Zoho deep link)

Status 2026-10-20: plan only. No live change made for any step below.

## Why this comes before the link goes on a resume

- The 9 calls in Supabase are real VAPI test calls from the owner's phone, not fictional data.
- A recruiter correction writes an outbox row and the worker sends it to the owner's real Zoho Recruit
  (`api/app/worker.py`, `correction_note`). A stranger with the demo password could therefore write to Zoho.

## Decisions

| # | Decision | Status |
|---|---|---|
| 1 | Data isolation: an `is_demo` flag in the same database. The demo login sees only demo rows; the owner (admin) sees all. The worker skips demo rows; demo edits never create an outbox row | DECIDED by the owner 2026-10-20 |
| 2 | Visitors may edit follow-up status and notes (reset nightly) but not field corrections | open, recommended |
| 3 | Demo password: given on request, not printed on the resume | open, recommended |
| 4 | Reviewer: agents only for now, a human (for example the mentor) optional | open, recommended |
| 5 | Show the Zoho link with Option 4: real fictional candidates in the owner's Zoho and an owner-only "Open in Zoho" link | DECIDED by the owner 2026-10-20 |

Zoho deep link (from the owner's own candidate URL, region `.com`):
`https://recruit.zoho.com/recruit/org935020705/EntityInfo.do?module=Candidates&id=<zoho_candidate_id>&submodule=Candidates`
The organisation number is an identifier, not a secret. It goes in an env setting (`ZOHO_RECORD_URL_TEMPLATE`), not in code.

## Part A: independent review (C3 step 6), read-only, no live change

Two separate reviewer agents (`ecc:security-reviewer`, `ecc:fastapi-reviewer`), each with the code and the live-check results.
Scope: login (hashing, cookie flags, session secret, logout, throttle behind Caddy and trust of `X-Forwarded-For`; the throttle is in
memory and resets on restart), CSRF on `PATCH`, data exposure (recording redirect, `raw_payload`, error text), secrets (VAPI private key
is full power, `.env` files, Caddy logs), demo-user abuse (what reaches Zoho, request size), headers, the HTTP/3 versus UDP 443 mismatch.
Output: `docs/SECURITY-REVIEW.md`, findings ranked; real ones fixed test-first; any live fix needs its own approval.

## Part B: C4 build (test-first, local first)

1. Migration 013: `is_demo` on `applicants`; the worker's claim query skips demo rows; correction code creates no outbox row for a demo
   applicant; list and detail queries scope by the user's role.
2. Fictional seed, about 8 people across HOT/MEDIUM/WARM/COLD, one "waiting for Zoho" row, one needs-review call; dates relative to
   now; text summaries and transcripts, no audio. Seed rows carry stored `zoho_candidate_id` values (step 4).
3. Nightly reset `app.demo_reset` (delete demo rows, re-seed), scheduled on the server at 03:00 Vancouver (host cron or systemd timer).
4. Zoho script, run once, idempotent (find by phone, add the note only if the record was created): about 8 fictional candidates and
   8 notes in the owner's own Zoho; ids saved with the seed definition. The reset never touches Zoho.
5. Owner-only `zoho_url` in the applicant detail response and an "Open in Zoho" button; visitors see "Zoho record: owner only".
6. Rotate the demo password with `users_cli rotate`; the new password goes to a file, never printed.

## Live steps (each needs explicit approval, real actions reported separately from tests)

Run the review (none) -> build and test locally (none) -> deploy with migration 013 -> run the Zoho script (about 8 candidates and
8 notes written to the owner's Zoho) -> seed and schedule the reset -> rotate the password -> outside checks and the owner's browser check
-> only then put the link on the resume.

## Not changed by this plan

Public visitors never reach Zoho. The live Zoho link is also shown by a live walkthrough (`owner` login and a real call) or a short
recording; the public site shows fictional data and the sync state.
