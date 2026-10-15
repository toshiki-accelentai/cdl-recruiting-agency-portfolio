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
