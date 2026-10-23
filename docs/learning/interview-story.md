# Interview story bank

One entry per work session (see `README.md` → "Session routine").
Write in my own words; Claude can check facts, not write the entry.

Template:

```
## YYYY-MM-DD — <topic>
- Predicted:
- Did:
- Why:
- Rejected option:
- Claude Code piece used (and why):
```

## 2026-10-12 — C1a 
1. I built login, a signed session cookie and roles.
2. To make it easy to log everyone out at once when a password changes or someone abuses the demo login (session_version).
3. Passwords are hashed with argon2id and a random salt, never stored as plain text.
- Rejected option: JWT. It can't be cancelled before it expires, so changing the password wouldn't log out people who are already in.
- Predicted: (C1b ordering prediction: to fill in)

## 2026-10-14 — Debug drills 1 and 2
- Bug 1: the name check in the correction code was flipped (a missing `not`), so calls that a recruiter had fixed stayed flagged "needs review".
- Bug 2: the worker's query had `NULL` where the saved Zoho id should be read, so the worker never got the id.
- Found: failing test, then the function or query, then the one item that didn't fit the pattern.
- Real-life impact: a corrected phone would create a duplicate candidate in Zoho. The worker only knew how to search by phone, and Zoho still had the old number.

## 2026-10-14 — Debug drill 3 (login)
- Bug: the password-change query set `session_version = 1` instead of `session_version + 1`, so the counter never moved and a login ticket handed out before the change still matched.
- Found: the failing test said an old login still got `200` instead of `401`, so I looked at the code that changes the password.
- Real-life impact: after rotating the demo password, people already logged in would stay logged in until their ticket expired (8 hours).
- Key idea: logout only throws away the ticket in one browser; the counter cuts off every earlier ticket at once.


## 2026-10-22 — Intake node review, readiness categories, simulated test calls
(Written by Claude at the owner's request, from this session's exchanges. Decisions are marked as the owner's; the code and the test run were Claude's.)
- Predicted: I wrote down a bucket (HOT/MEDIUM/WARM/COLD) for 7 spoken answers before any test. 5 of 7 matched at first. "Next week" did not match because the live description said 14 days; "Not for 3 days" did not match because the agent said HOT.
- Did: I asked for a review of the intake node. Claude found real bugs by running inputs: "2 days" and "tomorrow" became COLD, "13 days" became HOT, "2 years 6 months" became 0.5 years, an empty spoken phone number skipped the caller ID, and state and ZIP were only checked for being present. Claude fixed them with tests first.
- Why (my decisions): ZIP must be exactly 5 digits. The business timezone is Vancouver. "This week" and "next week" mean within 7 days. A start in exactly 3 days counts as within 3 days (HOT). The voice agent judges the answer and the code only maps four fixed answers; anything else becomes UNKNOWN, never a silent COLD.
- Rejected option: keep reading free text with patterns. It cannot cover "right now", "24 hours" or "not for 3 days". Also rejected: a new `readinessBucket` field. The live tool already had the four-answer list; only its description needed the rules.
- Claude Code piece used (and why): Claude ran 21 simulated chats (7 answers x 3 runs) with the save tool mocked, so there were 0 real calls and 0 n8n runs. This is why I could check the voice agent's judgement without booking anything. First run was not stable ("Next week" gave 7 days twice and 14 days once); after I fixed the rule it gave 7 days all 3 times.
- Mistake caught: Claude's first update of the live VAPI tool sent only `function` and silently removed the tool's webhook `server`. Claude found it, restored it from the saved copy, and now diffs the whole tool after every change.
