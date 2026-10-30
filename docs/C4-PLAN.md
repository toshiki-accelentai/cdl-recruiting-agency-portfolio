# C4 plan: a separate demo server (fictional data, nightly reset), then the independent review

Status 2026-10-20: plan only. No live change made for any step below.
Rewritten 2026-10-20: decision #1 changed from an `is_demo` flag to a separate demo server (owner's decision).

## Why this comes before the link goes on a resume

- The calls in Supabase are real VAPI test calls from the owner's phone, not fictional data.
- A recruiter correction writes an outbox row and the worker sends it to the owner's real Zoho Recruit
  (`api/app/worker.py`). A stranger with the demo password could therefore write to Zoho and read real callers
  (`docs/SECURITY-REVIEW.md` findings 1 and 2).

## Why a separate server and not an `is_demo` flag

A flag only works if every query remembers it. The first pass already found places that would leak: the 409 on a
phone conflict returns the real applicant's name and id (`corrections.py`), the To do counts include every call
(`todo.py`), and the change history mixes rows. A separate server with its own database and no Zoho or VAPI keys
cannot reach real data even if the code has a bug. This is the usual choice for a public demo (sandbox environment).

## Decisions

| # | Decision | Status |
|---|---|---|
| 1 | Separate demo server: same image, its own container and database, no Zoho credentials, no VAPI key, no shared secret, no worker | DECIDED by the owner 2026-10-20 (replaces the `is_demo` flag) |
| 2 | Where the demo database lives: (a) a Postgres container on hermes-vps, no published port, or (b) a new Supabase project | DECIDED by the owner 2026-10-20: (a) Postgres container on hermes-vps |
| 3 | Visitors may edit fields, follow-up status and notes on the demo; all reset nightly | DECIDED by the owner 2026-10-20 (as recommended) (safe now: nothing leaves the demo) |
| 4 | Demo password: given on request, not printed on the resume | DECIDED by the owner 2026-10-20 (as recommended) |
| 5 | Reviewer: agents only for now, a human (for example the mentor) optional | DECIDED by the owner 2026-10-20 (as recommended) |
| 6 | The real dashboard: admin only. Remove the `recruiter` user from the real instance; strangers only ever get the demo host | DECIDED by the owner 2026-10-20 (as recommended) |
| 7 | How Zoho is shown: on the real dashboard (owner login) with an owner-only "Open in Zoho" link, in a live walkthrough or a recording. The demo shows the sync state only ("waiting for Zoho" stays visible because no worker runs) | DECIDED by the owner 2026-10-20 (as recommended). Replaces the earlier "fictional candidates in the owner's Zoho" step, which is no longer needed |

| 8 | Proof of "production level" is the evidence (a 2-3 minute video of a real call reaching Zoho, the B2 Zoho-down drill, tests, this review), not the public demo. Until 10/31 the public demo is a showroom: fictional data plus one or two sample recordings. A public demo phone line (visitors call a demo agent and see their call appear; demo server only, no Zoho; call length cap, recorded-call notice, masked phones) is AFTER publish, if time allows | DECIDED by the owner 2026-10-20 |
| 9 | Hostnames (Cloudflare DNS, records set to "DNS only"): the PUBLIC DEMO keeps `cdl-demo.accelentai.com`; the REAL dashboard moves to `cdl-admin.accelentai.com` (one new A record to <server-ip>) | DECIDED by the owner 2026-10-23 (Option A, as recommended) |

Zoho deep link for the real dashboard (region `.com`):
`https://recruit.zoho.com/recruit/org935020705/EntityInfo.do?module=Candidates&id=<zoho_candidate_id>&submodule=Candidates`
The organisation number is an identifier, not a secret. It goes in an env setting (`ZOHO_RECORD_URL_TEMPLATE`), not in code.

## Part A: build (test-first, local first, no live change)

1. Config check: the app starts and serves pages with only `DATABASE_URL` and `SESSION_SECRET` set. `POST /calls` and
   `/call-reports` answer 503, the recording endpoint answers 503. Tests for each.
2. Fictional seed `app.demo_seed`: about 8 people across HOT/MEDIUM/WARM/COLD, one "waiting for Zoho" row, one
   needs-review call, one failed sync; dates relative to now; text summaries and transcripts, no audio. Refuses to run
   unless an explicit `DEMO_MODE=1` is set, so it can never be pointed at the real database by mistake.
2b. Sample recordings (owner decided 2026-10-20): one or two demo calls play a real-sounding recording. The demo
   server never asks VAPI: with `DEMO_RECORDINGS_DIR` set, `GET /api/calls/{id}/recording` serves a local file named in
   the seed (fixed names only, never a path from the request). The file comes from one fictional call the owner places to
   the real agent (a normal, realistic fictional name, number and city; the owner decided 2026-10-22 against any "Demo" label in the name), downloaded once from the VAPI dashboard.
   The file stays out of git (`.gitignore`) and is copied to a server volume. That one call is a real action: it also
   writes one row to the real database and one candidate to the owner's Zoho; delete or keep them, owner's call.
3. Nightly reset `app.demo_reset`: empty the demo tables and re-seed, also `DEMO_MODE=1` only.
4. Owner-only `zoho_url` in the applicant detail response and an "Open in Zoho" button on the real dashboard. UI part
   waits until the current UI work is merged.
5. `docs/SECURITY-REVIEW.md` findings 3 to 5 (error text and Zoho id for admin only, write rate limit) on the shared code.

## Part B: independent review (read-only)

Two separate reviewer agents (`ecc:security-reviewer`, `ecc:fastapi-reviewer`) against `docs/SECURITY-REVIEW.md` and the
Part A code, plus the items the first pass did not cover: Caddy config and live response headers, server `.env`
permissions, the network layout of the demo container. Real findings fixed test-first.

## Live steps (each needs explicit approval, real actions reported separately from tests)

1. Create the demo database (decision #2) and a `demo.` DNS record.
2. Deploy the demo container. Network: its own Docker network shared only with Caddy, so it cannot reach `cdl-api`,
   n8n or the real database; Caddy gets a `demo.` host block.
3. Run the seed, schedule the reset at 03:00 Vancouver (host cron or systemd timer), create the demo user
   (password written to a file, never printed).
4. Remove the `recruiter` user from the real instance (decision #6).
5. Outside checks: the demo host shows only fictional rows; `POST /calls` and the recording endpoint do not work there;
   the real host still needs the admin login. Then the owner's browser check.
6. Only then put the demo link on the resume.

## Not changed by this plan

Public visitors never reach Zoho, VAPI or the real database. The real pipeline (VAPI -> n8n -> API -> outbox ->
Zoho) is shown with the owner's login and a real call, or a short recording.
