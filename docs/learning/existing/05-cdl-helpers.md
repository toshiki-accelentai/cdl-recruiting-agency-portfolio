# U5 — `cdl_helpers.js`: the business logic, read side by side with Python

> **Goal:** read every function in the one file that decides "is this phone
> number real," "how many years of experience is that," and "is this callback
> time actually bookable" — then write each one's Python equivalent yourself.
> Source: `workflow-src/cdl_helpers.js` (187 lines, no dependencies).

## Why it matters most

This is the single source of truth pasted into multiple n8n Code nodes across
U3 and U4 (you already read it there without knowing it — "Validate Callback"
in U4 *is* this file's `validateCallback`). It's also the file you'll port to
Python first, once Phase A starts, because every later workflow — intake,
booking, a future Python API — depends on the same rules being applied the
same way everywhere. If this logic drifts between two copies, that's how you
get "the calendar said 9am was bookable but the phone workflow said it
wasn't."

Unlike U1–U4, there's no n8n canvas here — just plain JavaScript functions.
The exercise is different too: for each one, write what you think the Python
version looks like *before* you compare notes with me. That's the "read side
by side with Python" part.

## Five new ideas

1. **No library, so the code proves its own correctness.** JavaScript has no
   built-in IANA timezone database access beyond `Intl.DateTimeFormat`. The
   `zonedParts` → `offsetAt` → `localPartsToUtc` chain ([:69-100](../../../workflow-src/cdl_helpers.js#L69-L100))
   exists only because there's no `zoneinfo`-style module to just ask "what's
   the UTC offset for Vancouver on this date." Python has that built in —
   this is the single biggest language difference you'll hit.
2. **Round-trip verification instead of a formula.** `localPartsToUtc` doesn't
   compute the UTC time with a clever formula — it *guesses*, converts back to
   local time, and checks if it got the same answer, retrying up to 3 times
   ([:91-100](../../../workflow-src/cdl_helpers.js#L91-L100)). This handles DST transitions
   correctly without the code ever having to know when DST starts or ends.
3. **Algorithmic holiday dates, not a hardcoded list.** `nthWeekday` computes
   "the 3rd Monday of January" arithmetically for *any* year
   ([:102-106](../../../workflow-src/cdl_helpers.js#L102-L106)) instead of a table someone
   has to update every January.
4. **Regex cascade with order-dependent fallbacks.** `parseExperienceYears`
   ([:26-40](../../../workflow-src/cdl_helpers.js#L26-L40)) tries five different phrasings
   in a specific order — month ranges before single months, year ranges before
   single years — because a driver might say "3-5 years" or "8 months" or "no
   experience," and the function has to guess which shape it's looking at.
5. **`||=` as a fallback-fill pattern.** In `parseLocation`
   ([:56-65](../../../workflow-src/cdl_helpers.js#L56-L65)), `city ||= match[1].trim()`
   means "only fill `city` from the legacy free-text field if it's still
   empty" — used three times to patch structured fields from one legacy
   catch-all field without overwriting good data that's already there.

## Function by function

| Function | What it does | The interesting part |
|---|---|---|
| `clean` [:8-10](../../../workflow-src/cdl_helpers.js#L8-L10) | Trims a value, or returns `''` if it isn't a string. | Every other function calls this first — one place decides "what counts as empty." |
| `normalizePhone` [:12-17](../../../workflow-src/cdl_helpers.js#L12-L17) | Strips non-digits, adds a `1` country code if missing, returns E.164 (`+16727274656`) or `null`. | Rejects anything that isn't exactly 10 or 11 digits (with a leading `1`) — no attempt to fix an obviously wrong number. |
| `splitName` [:19-24](../../../workflow-src/cdl_helpers.js#L19-L24) | Splits "John Smith" into first/last. One word → `lastName` only, with `firstName: ''`. | A single-word name is assumed to be a last name, not a first name — a judgment call worth questioning. |
| `parseExperienceYears` [:26-40](../../../workflow-src/cdl_helpers.js#L26-L40) | Turns free text ("3 years 8 months", "under 6 months", "no experience") into a decimal number of years. | The order of the five regex checks *is* the logic — move one line and you change what gets matched first. |
| `classifyTemperature` [:42-48](../../../workflow-src/cdl_helpers.js#L42-L48) | Maps stated readiness text to `HOT`/`MEDIUM`/`WARM`/`COLD`. | Matches phrases ("right away", "one week"), not numbers — depends entirely on what the VAPI agent actually transcribes. |
| `parseLocation` [:50-67](../../../workflow-src/cdl_helpers.js#L50-L67) | Prefers structured `city`/`state`/`zipCode` args; falls back to parsing one legacy `driverLocation` string with a regex only for whatever fields are still missing. | The regex `^(.+?)(?:,\s*|\s+)([A-Za-z]{2})...` assumes "City, ST ZIP" or "City ST" — anything else falls through to "whole string is the city." |
| `zonedParts` [:69-84](../../../workflow-src/cdl_helpers.js#L69-L84) | Given a UTC `Date`, returns its year/month/day/hour/minute/weekday *as seen in Vancouver*. | Uses `Intl.DateTimeFormat(...).formatToParts()` instead of string-parsing a formatted date — parts come back as structured data, not text to re-parse. |
| `offsetAt` [:86-89](../../../workflow-src/cdl_helpers.js#L86-L89) | Given a UTC `Date`, returns Vancouver's current UTC offset in milliseconds (handles PST vs PDT). | Computed by *comparing* the same instant interpreted two ways — no hardcoded `-7` or `-8`. |
| `localPartsToUtc` [:91-100](../../../workflow-src/cdl_helpers.js#L91-L100) | Given "2026-09-25 10:00 Vancouver local time," returns the correct UTC `Date`. | The guess-check-retry loop from idea #2 — see below for why. |
| `nthWeekday` / `lastWeekday` [:102-112](../../../workflow-src/cdl_helpers.js#L102-L112) | Compute "3rd Monday of January" / "last Monday of May" for any year. | Pure date arithmetic — idea #3. |
| `observedDate` [:114-119](../../../workflow-src/cdl_helpers.js#L114-L119) | Shifts a fixed-date holiday off a weekend (Sat → Fri, Sun → Mon) — the "observed" federal rule. | |
| `federalHolidays` [:121-135](../../../workflow-src/cdl_helpers.js#L121-L135) | Returns a `Set` of 11 US federal holiday date strings for a given year. | A `Set` for O(1) `.has()` lookups — this is called once per `validateCallback` check. |
| `validateCallback` [:137-175](../../../workflow-src/cdl_helpers.js#L137-L175) | The function you already met in U4 — orchestrates everything above into "is this requested time actually bookable," and if so, returns `startUtc`/`endUtc`. | Every rejection reason (`past_time`, `weekend`, `holiday`, `before_open`, `after_close`, `ends_after_close`) is a distinct string, not just `false` — that's what lets node 4 in U4 build a specific, helpful caller message instead of a generic "no." |

## Why `localPartsToUtc` guesses instead of computing directly

This is worth sitting with, because it's the one piece of "clever" code in
the file. The problem: "10:00 AM Vancouver time" doesn't have one fixed UTC
offset — it's UTC-7 in summer (PDT) and UTC-8 in winter (PST), and the exact
switchover date moves every year. JavaScript's `Date` object only *knows*
either "the machine's local time" or UTC — it has no concept of "convert this
wall-clock time as if it were in Vancouver."

So the function fakes it:
1. Treat the requested local time as if it *were* already UTC (a wrong guess,
   off by the timezone offset).
2. Ask: "if this UTC instant were displayed in Vancouver, what wall-clock time
   would it show?" (`zonedParts`)
3. Compare that to what was actually requested. If they don't match, adjust by
   the difference and try again — up to 3 times, to be safe.
4. Once the round-trip matches, that guess *is* the correct UTC instant.

Python's standard library (`zoneinfo`, added in 3.9) can do this in one line:
`datetime(2026, 9, 25, 10, 0, tzinfo=ZoneInfo("America/Vancouver"))` already
*is* the correct instant — no round-trip needed, because Python's `datetime`
natively understands IANA timezones. This is the clearest example in the
whole file of "same problem, very different amount of code, purely because of
what the standard library gives you for free."

## Try it yourself — write the Python before you check

For each function below, write what you think the Python version looks like.
Don't peek at hints until you've tried.

1. `normalizePhone("(672) 727-4656")` — what should it return? Write the
   Python function.
2. `parseExperienceYears("3 years 8 months")` — trace through the regex
   cascade by hand. Which branch matches? What's the returned number?
3. `validateCallback` for a Saturday at 10am — which specific rejection
   reason fires, and in what order are the checks evaluated? (Order matters:
   what if a date is *both* a weekend *and* a holiday?)
4. Sketch the Python signature for `localPartsToUtc` using `zoneinfo`. How
   many lines does your version need compared to the 10 here?

## Break it & fix it

Two independent bugs to find by reading, not running:

1. **`splitName("Smith")`** returns `{ firstName: '', lastName: 'Smith' }`.
   Now trace `splitName("Cher")` — same result. Is "Cher" actually more likely
   to be a first name than a last name in this context? What real applicant
   name would this function mishandle, and where downstream (Zoho, the
   calendar event summary) would that surface as a visible mistake?
2. **`federalHolidays` is called with `p.year`** — the year of the requested
   *callback slot* ([:160](../../../workflow-src/cdl_helpers.js#L160)), not
   the year `now` currently is. Construct a specific date/time input where
   this distinction would matter (hint: think about a callback requested in
   December for a slot in January) — does the current code handle that
   correctly, or is there a case where it silently checks the wrong year's
   holiday list?

Bring me what you find on both — these are the kind of gaps that don't show
up in a happy-path manual test.

## Interview questions

**Q: Why does the timezone conversion code loop up to 3 times instead of
computing the answer directly?**
A: JavaScript's `Date` doesn't know about named timezones — it only knows UTC
and the machine's local time. So instead of a formula, I convert the guess to
Vancouver time, compare it to what was requested, and adjust — repeating
until it matches. It's solving for an unknown by iterating, not calculating
it in one step.

**Q: If you were porting this to Python, what would get dramatically
simpler?**
A: The whole timezone chain. Python's `zoneinfo` module understands IANA
timezones natively, so what's 30 lines of guess-and-check here becomes one
line — just pass the timezone into the `datetime` constructor and it's
already correct.

**Q: Why is holiday checking a `Set` instead of an array?**
A: It's checked on every single callback request, so I want that lookup to be
instant regardless of how many holidays are in the list — a `Set` does that,
an array would mean scanning every entry.

## Glossary added
IANA timezone · `Intl.DateTimeFormat` · UTC offset · DST (daylight saving
time) · E.164 · regex cascade · `Set` (data structure) · `zoneinfo` (Python)
