# B2 — "CRM is down" drill (runbook)

Claim being proved: **when Zoho Recruit is unreachable, callers are still served and no lead is
lost; when Zoho comes back, every lead is delivered automatically, exactly once.**

Why it works: a call is saved to Supabase first, together with a row in `outbox` ("send this to
Zoho"). The worker retries that row with a growing wait (30s, 60s, 120s ... max 15 min) until Zoho
answers. Zoho is never in the caller's path. Code: `api/app/worker.py`, `api/app/zoho.py`.

Last run: 2026-10-09 (not recorded; recording is a separate final task after Phase C).

## Before you start
- API and worker are up on hermes-vps; n8n CDL 02 + 03 are active (so web calls reach the API).
- Server access: `ssh -i ~/.ssh/<ssh-key> <ssh-user>@<server-ip>`. Server writes are run
  by hand in PowerShell (Claude Code's classifier blocks remote writes).
- Status board (read-only, prints no secrets):
  `api\.venv\Scripts\python.exe scripts\outbox_status.py --limit 5 --zoho`
  The `--zoho` check queries real Zoho from this PC, so `NOT IN ZOHO` is the truth, not an echo
  of the broken worker.
- Use new fictional phones (`206 555 01xx`) so nothing collides with older test candidates.

## Steps
1. **Baseline.** Run the status board. Expect `pending=0 failed=0` and every row `in Zoho`.
2. **Break Zoho.** Append an unreachable Zoho host to the server `.env`, then recreate only the
   worker (env vars are fixed when a container is created, so a restart is not enough):
   ```
   ssh ... "printf '\nZOHO_RECRUIT_API_DOMAIN=https://zoho-down.invalid\n' >> /opt/cdl-api/.env && cd /opt/cdl-api && sudo -n docker compose up -d --no-deps --force-recreate worker"
   ```
   `.invalid` can never resolve, so the worker sees a network error, exactly like a Zoho outage.
3. **Take calls while it is down.** 2 web calls in the VAPI dashboard, book all the way through.
   Expect: the AI says the details are saved and the call is booked (true: Supabase has them).
4. **Show the damage is contained.** Status board: new rows `pending`, `tries` rising, the next
   attempt further out each time, `last error` = `network error: ... Name or service not known`,
   `NOT IN ZOHO`.
5. **Restore.** Remove the line and recreate the worker:
   ```
   ssh ... "sed -i '/^ZOHO_RECRUIT_API_DOMAIN=/d' /opt/cdl-api/.env && cd /opt/cdl-api && sudo -n docker compose up -d --no-deps --force-recreate worker"
   ```
   Check: `docker exec cdl-api-worker-1 printenv ZOHO_RECRUIT_API_DOMAIN` prints nothing.
6. **Watch it drain.** The rows turn `sent` on their own when their `next attempt` comes due
   (up to a few minutes: the wait grew while Zoho was down). Recreating the worker does not lose
   or reset the rows; they live in Supabase.
7. **Count.** Calls in DB = outbox `sent` = candidates in Zoho; `pending=0 failed=0`.

## Gotchas
- `sed` alone is not a restore. Until the worker is recreated it keeps the broken host.
- The backoff means recovery is not instant. For a recording, keep the outage to a few minutes,
  or say the wait out loud. (Fast-forward would be `UPDATE outbox SET next_attempt_at = now()
  WHERE status = 'pending'`; say so on camera if used.)
- `database unavailable: failed to resolve host ...` in the worker log is the separate VPS DNS
  flake (todo B3), not Zoho. Do not show that log in a recording without explaining it.
- Leftovers: Zoho candidates and Supabase rows from the drill stay as evidence; delete the VAPI
  test calendar events by hand in Google Calendar.

## Result of the 2026-10-09 run
See `tasks/todo.md` (B2) for the numbers.
