# Recording plan: "CRM is down, no lead lost" + recruiter dashboard

One video, about **4 to 5 minutes**. The owner records it; Claude does not.
Runbook for the drill itself: `docs/B2-CRM-DOWN-DRILL.md` (last run 2026-10-09, not recorded).
The older `docs/LOOM-RECORDING-SCRIPT.md` is the n8n/Zoho walkthrough; this video replaces its
"show the result" part with the dashboard.

## What the video proves (say it in the first 15 seconds)

"When the CRM is down, callers are still served and no lead is lost. When the CRM comes back,
every lead arrives on its own, exactly once."

## Before you press record

- [ ] Rehearse the whole run once off camera, the same day.
- [ ] Two **fictional** callers ready, each with a new phone in the `206 555 01xx` range (never
      used before, so nothing matches an old test candidate). Example: "Casey Rivera", "Morgan Lee".
- [ ] A free weekday callback slot, 9 AM to 4:45 PM Pacific, for each caller.
- [ ] Browser tabs: dashboard (`cdl-admin`, signed in as `owner`), Zoho Recruit Candidates list,
      VAPI dashboard (for the web call). Status board in a terminal:
      `api\.venv\Scripts\python.exe scripts\outbox_status.py --limit 5 --zoho`
- [ ] **Never on screen:** the ssh command (it contains the server address), the server `.env`,
      n8n credentials, VAPI keys, the owner password, OAuth screens. Run the "break" and "restore"
      commands in a window that is off camera, and only say what you did.
- [ ] Close other dashboard records you do not want shown (the admin view shows Zoho ids and error
      text; that is fine, but check nothing real is in the list).
- [ ] In the rehearsal, check that a dashboard correction really reaches Zoho. The records do not
      show this verified on live yet; if it fails, leave the correction out of the video.
- [ ] Decide now: wait out the retry on camera, or fast-forward it (see step 6). If you fast-forward,
      you must say so on camera.

## Shot list

| Time | Show | Say (short) |
|---|---|---|
| 0:00–0:20 | Dashboard, Today's overview | What the system is: a voice agent takes after-hours driver calls; recruiters work from this desk; Zoho Recruit is the CRM. |
| 0:20–0:45 | One slide or the README diagram | The design rule: save to our own database first, and a delivery slip (the **outbox row**) is written in the same step. A background courier (the **worker**) carries it to Zoho and retries until Zoho answers. Zoho is never in the caller's path. |
| 0:45–1:00 | Status board, baseline | Everything is "sent", nothing pending, nothing failed. |
| 1:00–1:10 | (off camera) break Zoho | "I've pointed the worker at a Zoho address that can never answer, the same as a Zoho outage." |
| 1:10–2:10 | VAPI web call, caller 1 | Play the call through to a booked callback. Point out: the agent says the details are saved and the callback is booked. That is true: the database has them. |
| 2:10–2:40 | Dashboard: Call activity, then the applicant page | The new call is there with "Waiting to sync". Open it: name, ZIP, experience, readiness, transcript. The recruiter can already work this lead. |
| 2:40–3:00 | Status board | The row is `pending`, tries going up, each wait longer (30 s, 60 s, 120 s...), last error "network error". Zoho Candidates list: not there. |
| 3:00–3:10 | (off camera) restore Zoho | "Zoho is back." |
| 3:10–3:40 | Status board, then Zoho | The row turns `sent` by itself. Zoho has exactly one candidate for this phone, with the intake note. No duplicates. |
| 3:40–4:30 | Dashboard tour | To do list (who to call first: problems, then HOT to COLD, then earliest callback); mark one as called and use Undo; applicant page: correct a field (it goes to Zoho through the same courier), play a few seconds of the recording; Analytics in one sentence. |
| 4:30–4:50 | Back to the overview | One line on what is not finished (see "Say honestly" below), then thanks. |

Caller 2 is optional. Use it only if the first take is fast; it shows two leads draining.

## Step 6: waiting for the retry

The wait grows while Zoho is down (up to 15 minutes), so after a few minutes of outage the next try
can be several minutes away. Two honest options:

1. Keep the outage short (2 to 3 minutes) and cut the waiting out of the video, saying "a few minutes
   later".
2. Fast-forward: make every pending row due now
   (`UPDATE outbox SET next_attempt_at = now() WHERE status = 'pending'`) and **say on camera**
   that you did it and why.

## Say honestly (pick one line for the end)

- The demo site uses fictional data and has no CRM behind it; this video uses my own sandbox Zoho.
- Webhook authentication between the voice platform and n8n is not switched on yet: the first try
  broke inbound calls and was rolled back.
- Recruiter emails arrive in the inbox (owner confirmed, 2026-10-28 and again 2026-10-30).

## After recording

- [ ] Count: calls in the database = outbox `sent` = candidates in Zoho; `pending=0 failed=0`.
- [ ] Check the server `.env` is back to its normal keys
      (`docker exec cdl-api-worker-1 printenv ZOHO_RECRUIT_API_DOMAIN` prints nothing).
- [ ] Delete the test calendar events by hand in Google Calendar.
- [ ] Watch the video once for anything secret on screen (address bar, terminal, notifications).
- [ ] Add a line to `tasks/todo.md`: date, real actions (calls placed, Zoho writes), and the video link.

## If something goes wrong on camera

Stop, fix the cause off camera, and start a clean take. Do not troubleshoot on camera.
