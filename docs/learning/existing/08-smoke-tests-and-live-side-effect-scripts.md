# U8 — Smoke tests and live-side-effect scripts

> **Time estimate:** ~60–70 min on paper; at your real U-phase pace expect
> closer to 2–3 hours. The seven scripts total under 1,000 lines, but most of
> it is the same "build a throwaway n8n workflow" shape repeated with small
> variations — skim the repeats once you've traced the first one closely.
>
> **Everything in this doc is read-and-trace.** These scripts do make real
> calls: they activate workflows on the n8n instance at `N8N_BASE_URL` (your
> own copied workflows, not n8n cloud) and write to the Zoho and Google
> Calendar accounts behind them. This is your separate portfolio project,
> not the agent shipped to the client, so running one is low-stakes — but
> still read a script's dry-run output (where it has one) first, and note
> what it left behind. (Where this doc says "production workflows," it means
> the four deployed copies on that instance.)
>
> **Goal:** understand the scripts that are allowed to touch the *live*
> system — `scripts/smoke_test_google_calendar.py` (205 lines),
> `scripts/smoke_test_modular_suite.py` (187),
> `scripts/verify_reported_workflow_fixes.py` (skim, 183),
> `scripts/seed_zoho_candidate_batch.py` / `seed_zoho_loom_candidate.py`
> (skim both), `scripts/delete_zoho_note.py` /
> `scripts/delete_google_calendar_event.py` — and why their safety model is
> necessarily different from U7's dry-run-by-default generators and
> deployers.

## Why it matters most

U7's scripts (`deploy_n8n_suite.py`, `deploy_vapi_tool.py`) are safe to run
any time because they default to printing a diff and doing nothing. That
trick doesn't work here. A **smoke test** only proves anything by actually
making the real call — activating a real (if temporary) workflow, hitting a
real webhook, writing a real (if fictional) Zoho Note or Google Calendar
event. There's no dry-run version of "does this webhook actually work." So
this doc is about the *other* half of safe automation: not "default to
doing nothing," but "do the real thing, in the smallest, most contained way
possible, and guarantee cleanup even if it fails halfway through." This is
exactly the discipline the project's own operating rule demands — "activate
a workflow only for a deliberate test/demo window, then deactivate again
immediately" — except here it's enforced by code structure (`try`/`finally`),
not just a rule someone has to remember.

## Six new ideas

1. **Python can't talk to Zoho or Google directly, so these scripts don't
   try.** Both APIs are OAuth-only, and the only valid, auto-refreshing OAuth
   token lives inside **n8n's own credential store** — not in `.env`, not
   anywhere Python can read it (see U3's Zoho quirk, and
   `zoho_request`/`google_request` from U7). So when a script needs to read
   or write Zoho/Calendar *directly* (the two smoke tests, `verify_reported_
   workflow_fixes.py`, both delete tools, and the Loom script's verifier), it
   **builds a tiny, single-purpose n8n workflow in Python**, creates it,
   activates it, calls its webhook once, and deletes it. n8n is being used as
   an authenticated HTTP proxy — the only thing Python talks to directly is
   the n8n Workflows API (`deploy_n8n_workflow.request`, reused unchanged
   from U7) plus the webhook URLs. The exception is `seed_zoho_candidate_
   batch.py`, which builds no temp workflow at all: it just POSTs to the real
   Intake webhook, because the real Intake workflow already does the Zoho
   write.
2. **Activate → call → deactivate → delete is `try`/`finally`-wrapped,
   nested.** Look at `smoke_test_google_calendar.py:182-201`,
   `smoke_test_modular_suite.py:159-170` or
   `delete_google_calendar_event.py:39-53`: `workflow_id = None` is set
   first, then the whole sequence — create, activate, call the webhook,
   assert — sits *inside* the `try`. The `finally` checks `if workflow_id:`
   (so a failed create doesn't try to clean up something that was never
   made), then deactivates and deletes in a nested `try`/`finally` so that
   even if deactivation itself fails, deletion still runs. Two scripts
   (`delete_zoho_note.py:73-82` and `verify_reported_workflow_fixes.py`'s
   `temporary_call`, [:114-124](../../../scripts/verify_reported_workflow_fixes.py#L114-L124))
   use a variant: create *before* the `try`, so no `None` guard is needed —
   if the create raises, the `try` is never entered and there's nothing to
   clean up. Both shapes are correct; they're two ways of answering "what
   if the create itself fails." This is the literal code enforcing "default
   to inactive" — not a comment, a guarantee that survives an exception.
3. **Three different "how much mess is left behind" tiers, chosen on
   purpose per script.** (a) **Zero trace**: the two `smoke_test_*.py`
   scripts fabricate candidate data *in memory* inside a throwaway code node
   instead of writing to Zoho at all, create a real Calendar event only to
   immediately delete it and confirm the deletion, and delete the temporary
   workflow itself. (b) **One pinned fixture, not disposable**:
   `verify_reported_workflow_fixes.py` reuses the *same* synthetic Candidate
   every time (found by a fixed `PHONE`), writes real diagnostic Notes
   through the real production workflows, then deletes only those three
   Notes — by the exact IDs it just read back, filtered by exact title
   match — the Candidate itself stays. Note the link between scripts: that
   `PHONE` (`+12025550111`) and the name in its payload ("Marcus Thompson")
   are the *first profile* in `seed_zoho_candidate_batch.py`'s `PROFILES` —
   the "existing" fixture is one of the seeded candidates. (c)
   **Deliberately persistent**: `seed_zoho_candidate_batch.py` (ten
   candidates) and `seed_zoho_loom_candidate.py` (one demo candidate) push
   fictional applicants through the real intake flow and **leave the
   candidates there** — that data is for Phase C's dashboard to have
   something to show later. What they do *not* leave behind is an active
   workflow: both are dry-run by default (`--apply` to write), both activate
   Intake and Booking for the run, and both deactivate them in a `finally`.
   So "persistent" applies to the data, not to the workflow state. Same
   toolkit, three different answers to "what do we keep."
4. **Deterministic IDs reappear, this time for predicting a URL before the
   thing exists.** `smoke_test_modular_suite.py`'s `base32hex_number()`
   ([:28-36](../../../scripts/smoke_test_modular_suite.py#L28-L36)) turns the
   test slot's Unix timestamp into a base-32 string, and
   `calendar_event_id = f"cdlslot{...}"` is built from it *before* the event
   is created — so the script can compute the exact Google Calendar event
   URL it expects the real booking subworkflow to create, and then check
   `eventIdMatches` against that prediction. Same idea as U4's deterministic
   event ID, reused here as a *test oracle* instead of a production
   idempotency guard.
5. **Test slots are scheduled far enough in the future that they can't
   collide with real data.** `next_test_slot()` adds 370 days;
   `smoke_test_google_calendar.py` adds 365. Far enough out that no real
   candidate's actual callback could already occupy that slot, so a smoke
   test can never silently clobber (or be blocked by) a real booking. (The
   modular suite also nudges forward to a weekday at 10:00 Vancouver time,
   so the slot looks like a legal booking slot.)
6. **None of these seven scripts are referenced anywhere in `tests/`.**
   That's not a gap — it's a boundary. A script whose entire purpose is "go
   cause one real side effect and report what happened" can't be
   meaningfully asserted against offline; the closest thing to verification
   *is* running it once, by hand, and reading the JSON it prints. That's
   exactly what the project `CLAUDE.md` means by "a change is only done when
   a real test call has been placed... not when the workflow saves without
   error" — these scripts are how that real test call gets placed without
   leaving a mess.

## Walkthrough — the two smoke tests

| Function | What it does | The interesting part |
|---|---|---|
| `http_node` [smoke_test_google_calendar.py:22-43](../../../scripts/smoke_test_google_calendar.py#L22-L43) | Builds one HTTP Request node pre-wired with the Google Calendar OAuth credential, retries, and a 10s timeout. | Identical in shape to U7's `zoho_request`/`google_request` builders, but defined again here rather than imported — these throwaway test workflows don't reuse the production builder module at all, they have their own minimal copy. `smoke_test_modular_suite.py` and `delete_google_calendar_event.py` *do* import this one copy from here, though — so it's shared across the three live-side-effect scripts that need it, just not with the U7 production builders. |
| `build_workflow` [:46-162](../../../scripts/smoke_test_google_calendar.py#L46-L162) | Wires up an 8-node, single-purpose workflow: webhook in → FreeBusy check → build event body → create → read back → delete → confirm gone → report. | The "Report" code node at the end reads every upstream node by name (`$('Create Event')`, `$('Confirm Deleted')`, …) and reduces the whole run to four booleans (`freeBusyOk`, `created`, `fetched`, `deletionConfirmed`) — the smoke test's entire verdict is "are these four things true," not "did nothing throw." |
| `main` [:171-201](../../../scripts/smoke_test_google_calendar.py#L171-L201) | Builds a unique path/event ID, creates+activates the temp workflow, calls its webhook, checks all four booleans, prints diagnostics and raises if any failed — then *always* deactivates and deletes, even on failure. | `if not all(public_result.values()): ... raise RuntimeError(...)` happens *before* the `finally` block's cleanup runs (since it's inside the `try`) — so the raised error still propagates to the caller/shell *after* cleanup completes, giving you both a non-zero exit code and a clean n8n account. |
| `next_test_slot` / `base32hex_number` [smoke_test_modular_suite.py:28-36](../../../scripts/smoke_test_modular_suite.py#L28-L36), [:58-63](../../../scripts/smoke_test_modular_suite.py#L58-L63) | Pick a weekday 10 AM slot 370 days out; encode its timestamp as a predictable event-ID suffix. | Two independent safety tricks stacked: far-future scheduling avoids colliding with real data, and encoding the *same* timestamp the same way every time means the predicted ID and the real one will match only if the booking logic actually used that exact time — a wrong time would silently produce a mismatched ID, which the test would then catch as `eventIdMatches: false`. |
| `booking_caller` [:66-123](../../../scripts/smoke_test_modular_suite.py#L66-L123) | Builds a 7-node temp workflow that fabricates fake candidate JSON in a code node, feeds it straight into the *real* Calendar Booking subworkflow (by its real, already-deployed workflow ID from `WORKFLOWS`), then deletes the event it creates and confirms deletion. | This never writes to Zoho at all — it calls Booking directly via `executeWorkflow`, the same node type Intake itself uses in production, bypassing Intake/the Zoho Candidate write entirely. It's testing "does the Booking subworkflow correctly book and idempotently handle a slot," isolated from "does the Zoho write work" (that's what `verify_reported_workflow_fixes.py` is for). |
| `test_public_workflow` [:126-131](../../../scripts/smoke_test_modular_suite.py#L126-L131) | Activate one production workflow, call its real public webhook once, deactivate — wrapped so deactivation always runs. | Unlike the throwaway test workflows, Routing/Intake/Post-Call here are the **actual production workflows** (`WORKFLOWS["routing"]`, etc.) — this briefly, deliberately activates and deactivates the real thing, which is exactly the "deliberate test/demo window" the project's operating rule describes, not a copy of it. |
| `main` [:134-183](../../../scripts/smoke_test_modular_suite.py#L134-L183) | Runs routing, invalid-intake, post-call, and booking checks in sequence, all under nested `try`/`finally` so Booking (needed as a subworkflow target) is deactivated last regardless of what happened above it. | The invalid-intake check sends `{"toolCalls": []}` on purpose — it's verifying the *graceful-failure* path (U3's guard-node idea) actually returns a `results` array instead of crashing, using real malformed input against the real workflow. |

## Walkthrough — the rest

| Script | Pattern | Worth noticing |
|---|---|---|
| `verify_reported_workflow_fixes.py` | `main()` first POSTs a synthetic intake and a synthetic post-call to the **real** Intake and Post-Call webhooks, then runs a temp workflow that *reads* the Candidate (found by `PHONE`) and its Notes, retrying up to 10×; then a second temp workflow deletes the three diagnostic Notes by ID. | Two things to notice. (1) It never activates Intake or Post-Call — it assumes they're *already* active, unlike the seed scripts and the modular smoke test, which switch them on and off themselves. (2) Deleting the Notes it just read back, filtered by exact title, not "every Note on this candidate," is the same narrow-and-exact instinct as `redact()` in U6. |
| `seed_zoho_candidate_batch.py` | Dry-run by default. With `--apply`: activates Booking + Intake, POSTs ten hardcoded fictional profiles (`PROFILES`) through the real Intake webhook with realistic VAPI-shaped payloads, does one routing check, and deactivates both workflows in a `finally`. | The `finally` cleans up *workflow state* but deliberately not *data* — the ten Candidates stay (idea 3c). Compare with `seed_zoho_loom_candidate.py`: same shape for one candidate, plus a `--verify-only` mode and a temp verifier workflow that reads the Candidate and Notes back to confirm the write really landed. |
| `delete_zoho_note.py` / `delete_google_calendar_event.py` | CLI tools. Note: dry-run unless `--apply`, and the ID must be all digits. Calendar event: no dry-run, but the ID must start with `"vapitest"` or `"vapivapitest"`. | These are the companion cleanup tools for (a) and (b)'s "found something left over, delete *this one specific thing*" case — same `--apply` discipline as U6's `deploy_vapi_tool.py` for the Note tool; the Calendar tool trades dry-run for a naming guard. Note they use the two different create-before-`try` / create-inside-`try` shapes from idea 2. |

## Try it yourself — predict, then trace

1. In `smoke_test_modular_suite.py.main()`, the Booking workflow is activated
   once, outside the per-check `try`/`finally` blocks, and deactivated in one
   outer `finally`
   ([:143-172](../../../scripts/smoke_test_modular_suite.py#L143-L172)).
   Which of the invalid-intake, post-call and booking checks can actually
   reach Booking? (For invalid-intake, look at what `Intake Valid?` does with
   a false result in `cdl-02-applicant-intake.json`.) Given that, what's the
   real reason Booking is switched on for the whole span — and is "a
   sub-workflow must be active to be called" something this repo ever
   demonstrates, or just an assumption the scripts are written around?
2. If `smoke_test_google_calendar.py`'s `Create Event` call fails (say,
   Google returns a 409 because the fabricated event ID collided with
   something), does `Delete Event` still run? Trace the connections built at
   [:152-156](../../../scripts/smoke_test_google_calendar.py#L152-L156) and
   the `onError: continueRegularOutput` setting baked into every `http_node`
   to answer.
3. `delete_google_calendar_event.py`'s guard is `not sys.argv[1].startswith(
   "vapitest") and not sys.argv[1].startswith("vapivapitest")`
   ([:19](../../../scripts/delete_google_calendar_event.py#L19)). Would it
   accept the ID `"VAPITEST12345"` (uppercase)? Would it accept
   `"myvapitest99"`? What does that tell you about how strong a safety net
   this actually is?
4. Of the seven scripts, sort them into two groups: those that switch the
   production workflows they depend on on and off themselves, and those
   that assume the workflows are *already* active. Which group is
   `verify_reported_workflow_fixes.py` in
   ([:133-157](../../../scripts/verify_reported_workflow_fixes.py#L133-L157))?
   What would happen if you ran it today with Intake and Post-Call
   inactive, as the project's operating rule says they should be?

## Break it & fix it

1. **Same cleanup goal, two shapes — break the one that looks unguarded.**
   `delete_zoho_note.py:main()`
   ([:73-82](../../../scripts/delete_zoho_note.py#L73-L82)) creates the
   workflow *before* the `try` and has no `if workflow_id:` check, while
   `delete_google_calendar_event.py` sets `workflow_id = None`, creates
   *inside* the `try`, and guards the `finally`. (a) If the create POST
   raises in `delete_zoho_note.py` (bad API key, network drop), what runs —
   and is anything left in n8n? (b) Now suppose a tidy-minded refactor moves
   that create *inside* the `try` but keeps the unguarded `finally`. What
   exact error does the `finally` raise when the create fails, and what
   happens to the original error you actually wanted to see? That's the
   problem the `workflow_id = None` + guard shape solves.
2. **The pinned-fixture script says it "uses an existing" Candidate, but
   `main()` doesn't start by looking for one.** The `Capture Synthetic
   Candidate` node throws `synthetic_candidate_not_found` if the Zoho search
   for `PHONE` comes back empty
   ([:57-61](../../../scripts/verify_reported_workflow_fixes.py#L57-L61)).
   Trace `main()` ([:127-169](../../../scripts/verify_reported_workflow_fixes.py#L127-L169))
   from the top. Suppose someone deleted every Zoho candidate with a
   "test"-looking name before a demo, including this one: what is the first
   thing the script does with that `PHONE`, and what does it do to the
   Candidate? Then explain what the `for _ in range(10)` retry loop with
   `time.sleep(1)` is protecting against. Finally: if it *did* fail with that
   thrown error inside the temp workflow, what would the Python side
   actually show — the string `synthetic_candidate_not_found`, or something
   less helpful? (Check what `call()` does with a non-2xx response.)

Bring me what you find on both.

## Interview questions

**Q: Why can't these scripts just use `urllib.request` to call the Zoho or
Google API directly, the way `export_config.py` calls VAPI's API in U6?**
A: VAPI accepts a static private-key header; Zoho and Google Calendar are
OAuth-only, and the only place holding a valid, auto-refreshing access token
is n8n's own credential store — nothing Python-side has it, and shouldn't,
since that's exactly the kind of secret the project's `.env`/git-ignore rules
are protecting against. So instead of reimplementing OAuth token refresh in
Python, the scripts that need to touch those systems build a tiny n8n
workflow whose one job is "make this one authenticated call," run it once
through n8n's existing credential, and tear it down. n8n becomes the
authenticated HTTP client; Python just orchestrates when it runs. (The seed
scripts are the one exception — they go through the real Intake webhook,
which already does the Zoho write.)

**Q: These scripts aren't in the automated test suite at all. If you were
explaining that gap to a reviewer, how would you frame it — as a missing
test, or as something else?**
A: As something else, deliberately. An offline test suite (`unittest`, no
network) can only check things that are deterministic and local — structure,
generated JSON, pure functions. These scripts' entire value is a real side
effect against a live third-party system; there's no meaningful way to run
them "offline" without turning them into something that no longer proves
anything. The actual verification step is running the script once, reading
the JSON report it prints, and — per this project's own rule — not calling a
fix "done" until that's happened.

**Q: Three different scripts leave three different amounts of data behind
(nothing, a few Notes on a pinned fixture, or a whole batch of new
candidates). How would you defend that as a deliberate design instead of
inconsistency?**
A: Each one answers a different question, and the right cleanup policy
follows from the question. A smoke test is asking "does this workflow still
work" — the answer doesn't need evidence left behind, so leave none. The
fixture-verification script is asking "did this specific bug fix actually
take effect in Zoho" — it needs a stable, known starting point to compare
against every time, so the Candidate stays pinned and only the test Notes it
created get cleaned up. The seed script is asking "give me realistic-looking
data to build a dashboard against" — persistence is the entire point. But
even there the workflows get switched back off in a `finally`; only the data
stays. Same toolkit, three answers, because the cleanup policy should follow
from what the script is trying to prove, not from a single blanket rule.

## Concept check

Plain Python (and one timezone/SQL-adjacent) comprehension questions — these
are for understanding the language, not for rehearsing an interview answer.

1. **`try`/`finally` nesting order.** In
   `delete_google_calendar_event.py:48-53`:
   ```python
   finally:
       if workflow_id:
           try:
               request("POST", f"{base}/api/v1/workflows/{workflow_id}/deactivate", key)
           finally:
               request("DELETE", f"{base}/api/v1/workflows/{workflow_id}", key)
   ```
   If the `deactivate` call raises an exception, does the `DELETE` call still
   run? If *both* raise, which exception does the caller of `main()`
   ultimately see?
2. **Boolean precedence / De Morgan's law.** The full guard at
   `delete_google_calendar_event.py:19` is
   `len(sys.argv) != 2 or not A.startswith(x) and not A.startswith(y)`
   with no parentheses. (a) Python binds `and` tighter than `or` — add the
   parentheses Python is implicitly using. (b) Rewrite the
   `not ... and not ...` half as a single `not (... or ...)` and confirm
   they're equivalent. (c) Why is the missing-argument check safe in the
   first position — what would `sys.argv[1]` do if the length check were
   evaluated *after* it?
3. **Dict comprehension.** `smoke_test_google_calendar.py:152-156` builds
   the whole `connections` object with:
   ```python
   names = [node["name"] for node in nodes]
   connections = {
       names[index]: {"main": [[{"node": names[index + 1], "type": "main", "index": 0}]]}
       for index in range(len(names) - 1)
   }
   ```
   What does this produce for a 3-node list `["A", "B", "C"]`? Why
   `range(len(names) - 1)` and not `range(len(names))`?
4. **`zip` for pairwise iteration.** `smoke_test_modular_suite.py:117-118`
   does the same job a different way:
   ```python
   for left, right in zip(nodes, nodes[1:]):
       connections[left["name"]] = {"main": [[{"node": right["name"], ...}]]}
   ```
   Explain what `zip(nodes, nodes[1:])` actually produces, step by step, for
   `nodes = ["A", "B", "C"]`. Which of the two styles (this one, or #3's
   index-based comprehension) would you rather maintain, and why?
5. **`divmod` and base conversion.** `base32hex_number()`
   ([smoke_test_modular_suite.py:28-36](../../../scripts/smoke_test_modular_suite.py#L28-L36)):
   ```python
   while value:
       value, remainder = divmod(value, 32)
       encoded = alphabet[remainder] + encoded
   ```
   Walk through what `divmod(value, 32)` returns, and explain in your own
   words why repeatedly taking `remainder` and shrinking `value` this way
   converts a base-10 integer into a base-32 string. What would break if
   `value` started at `0`? (Hint: look at the one line above the `while`
   loop — why does it exist?)
6. **Naive vs. timezone-aware datetimes.** `next_test_slot()`
   ([smoke_test_modular_suite.py:58-63](../../../scripts/smoke_test_modular_suite.py#L58-L63))
   builds a time in `ZoneInfo("America/Vancouver")`, then calls
   `.astimezone(timezone.utc)` before turning it into a string. What's the
   difference between a "naive" and an "aware" Python `datetime`, and why
   would sending a naive Vancouver-local timestamp (no UTC offset attached)
   to a webhook be a real bug waiting to happen, rather than just a style
   preference?

## Glossary added
live side-effect script · smoke test (real call, not a mock) · OAuth proxy
(via n8n) · pinned fixture vs. disposable test data · test oracle (predicted
ID) · far-future test scheduling (collision avoidance) · naive vs.
timezone-aware datetime
