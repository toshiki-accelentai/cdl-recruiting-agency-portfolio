# U6 — How the Python scripts call APIs

> **Goal:** read `scripts/export_config.py` and `scripts/deploy_vapi_tool.py`
> closely enough to explain, line by line, how a plain Python script (no
> framework, no requests library) talks to VAPI and n8n's HTTP APIs, and why
> `deploy_vapi_tool.py` is built to be safe to run against a live system.
> Source: `scripts/export_config.py` (135 lines), `scripts/deploy_vapi_tool.py`
> (103 lines).

## Why it matters most

Everything in U1–U5 was about the *running system* (n8n workflows, the VAPI
assistants, the JS helper file). This is the first doc about the tooling that
*talks to* that system from your own machine — the same shape of code you'll
write in Phase A when the Python API calls Zoho's API instead of a human
reading a JSON export. `export_config.py` is the read-only half (GET, dump to
disk, redact secrets); `deploy_vapi_tool.py` is the read-write half (GET,
diff, only then maybe PATCH). Read them as a pair: one shows you how to talk
to an API safely when you're only looking, the other shows you how to talk to
it safely when you're about to change something live.

## Five new ideas

1. **`urllib.request`, not `requests`.** Both scripts use only Python's
   standard library — no `pip install` needed to run them. `requests` is
   nicer to write, but `urllib.request.Request(...)` +
   `urllib.request.urlopen(...)` does the same job: build a request object
   with a method/headers/body, open it, read the response
   ([export_config.py:87-91](../../../scripts/export_config.py#L87-L91)).
2. **A custom `User-Agent` header is load-bearing, not decoration.** VAPI's
   WAF (web application firewall) rejects Python's default urllib
   `User-Agent` string with a 403 — so both scripts send `"curl/8.0"` instead
   ([export_config.py:89](../../../scripts/export_config.py#L89),
   [deploy_vapi_tool.py:42](../../../scripts/deploy_vapi_tool.py#L42)). This
   is exactly the kind of "the docs don't mention this, the error message
   doesn't explain it either" fact you only get from hitting the wall once —
   see the platform quirks in the project `CLAUDE.md`.
3. **Read before you write.** `deploy_vapi_tool.py` always does `GET` first
   ([:82](../../../scripts/deploy_vapi_tool.py#L82)), builds the payload it
   *would* send, and only calls `PATCH` if that payload actually differs from
   what's live ([:90-97](../../../scripts/deploy_vapi_tool.py#L90-L97)). It
   is structurally incapable of blindly overwriting — it always knows what it
   is about to change before it changes it.
4. **Dry-run is the default, not a flag you have to remember.** Running the
   script with no arguments only prints what *would* change
   ([:93-95](../../../scripts/deploy_vapi_tool.py#L93-L95)). You must type
   `--apply` to write anything, and `--repoint-server` (a second, separate
   flag) is required on top of `--apply` before the script will touch the
   live webhook URL ([:71-74](../../../scripts/deploy_vapi_tool.py#L71-L74)).
   Two opt-ins for the more dangerous action, one for the safer one.
5. **Recursive redaction walks the whole tree, not a fixed list of fields.**
   `redact()` in `export_config.py` doesn't know in advance which keys will
   hold secrets in an arbitrary n8n workflow export — it recurses into every
   dict and list it finds, checking each key against `SECRET_KEYS` and every
   string value against two regexes for things that *look* like a secret even
   under an unknown key name
   ([:65-84](../../../scripts/export_config.py#L65-L84)).

## Function by function — `export_config.py`

| Function | What it does | The interesting part |
|---|---|---|
| `load_env` [:51-62](../../../scripts/export_config.py#L51-L62) | Reads `.env` by hand — split on the first `=`, strip quotes — into a plain `dict`. | No `python-dotenv` dependency. `utf-8-sig` handles a `.env` saved with a BOM (byte-order mark) from some Windows editors, which would otherwise leave an invisible character glued to the first key. |
| `redact` [:65-84](../../../scripts/export_config.py#L65-L84) | Recursively replaces secret values with a fixed placeholder string. | Two different secret-detection strategies layered together: "this key name is always sensitive" (`SECRET_KEYS`) and "this string's *shape* looks like a token even if the key isn't" (`ZOHO_TOKEN_RE`, `LONG_HEX_RE`). |
| `get` [:87-91](../../../scripts/export_config.py#L87-L91) | Does one authenticated GET and returns parsed JSON. | 60-second timeout — an API call has to fail loudly on a hang, not block the script forever. |
| `write` [:94-97](../../../scripts/export_config.py#L94-L97) | Writes formatted JSON to disk, creating parent folders if needed, and prints what it wrote. | `ensure_ascii=False` — keeps non-English text (e.g. a Japanese name in test data) readable in the file instead of escaped as `\uXXXX`. |
| `main` [:100-134](../../../scripts/export_config.py#L100-L134) | Loads `.env`, loops over the hardcoded VAPI assistants/tools and n8n workflows, redacts and writes each one. | Strips volatile metadata (`updatedAt`, `versionId`, …) before writing ([:126](../../../scripts/export_config.py#L126)) — otherwise every re-export would show a diff even when nothing meaningful changed. |

## Function by function — `deploy_vapi_tool.py`

| Function | What it does | The interesting part |
|---|---|---|
| `load_env` [:22-32](../../../scripts/deploy_vapi_tool.py#L22-L32) | Same pattern as `export_config.py`'s version — these two files don't share a common module, so the parsing logic is duplicated. | Worth asking: if `.env` parsing needed a bug fix, how many files would you have to remember to fix? (There's no shared `env.py` yet.) |
| `request` [:35-52](../../../scripts/deploy_vapi_tool.py#L35-L52) | A generic GET/PATCH helper: builds the request, sends it, and on an HTTP error re-raises with the response body attached. | `except urllib.error.HTTPError` catches *only* HTTP-level failures (4xx/5xx) — a malformed URL or a DNS failure would raise a different exception and isn't handled here. |
| `build_payload` [:55-61](../../../scripts/deploy_vapi_tool.py#L55-L61) | Takes the desired JSON contract, drops the `id` field, and — unless explicitly told not to — copies the live server URL into the payload before sending. | This is the safety mechanism from idea #4 made concrete: even if you edited `server.url` in the desired JSON file by accident, the script overwrites your edit with what's actually live, unless you pass both flags. |
| `project_live` [:64-67](../../../scripts/deploy_vapi_tool.py#L64-L67) | Walks the *desired* dict's shape and pulls out only the matching keys from `live`, recursively. | This is what makes the diff meaningful: VAPI's live tool object has many fields the desired file doesn't care about (timestamps, org IDs, …). Comparing `live == payload` directly would show a "change" on every run just from those extra fields. `project_live` throws them away first. |
| `main` [:70-98](../../../scripts/deploy_vapi_tool.py#L70-L98) | Parses flags, loads the desired contract, fetches live, builds the payload, projects live down to the same shape, compares, and only then (maybe) applies. | The comparison order is: build the *would-send* payload first, *then* diff against a same-shaped projection of live — never diff the raw live object against the raw desired file, because they're different shapes on purpose (live carries fields desired never will). |

## Try it yourself — predict, then trace

For each one, predict the answer first, then trace the actual code to check.

1. If you ran `python scripts/export_config.py` with a `.env` that has the
   wrong `VAPI_PRIVATE_KEY`, what's the first line of output you'd see, and
   where in the code does that failure get raised? (Hint: look at what `get`
   does when `urllib.request.urlopen` gets a 401.)
2. Run `deploy_vapi_tool.py` with no flags at all, twice in a row, assuming
   nothing changed on the VAPI side between runs. What does the second run
   print that's different from the first, if anything? Why?
3. Suppose `tool.logApplicantInfo.desired.json` on disk has a *different*
   `server.url` than what's live. You run the script with just `--apply` (no
   `--repoint-server`). Trace `build_payload` by hand — does the URL that
   actually gets sent to VAPI come from the desired file or from live?
4. `export_config.py`'s `redact()` checks `LONG_HEX_RE` (32+ hex chars)
   against every string in the tree, not just fields named like secrets. Find
   a *non-secret* value somewhere in an n8n workflow export that could
   accidentally match a 32+ character hex-looking string and get redacted by
   mistake. (Hint: n8n node IDs and workflow IDs are often long
   alphanumeric strings — check whether they're actually hex-only.)

## Break it & fix it

Two things to find by reading, not running:

1. **`load_env` is duplicated in both files, byte-for-byte identical logic.**
   If someone later needs `.env` values to support inline comments after the
   value (`KEY=value  # note`), and only fixes `export_config.py`'s copy,
   what breaks the next time `deploy_vapi_tool.py` runs against a `.env` that
   uses that new comment style? Where exactly would it fail?
2. **`build_payload`'s repoint guard checks `if not repoint_server and
   live_url:`** ([:59](../../../scripts/deploy_vapi_tool.py#L59)). Trace what
   happens if `live_url` is `None` (say, the live tool has never had a
   `server.url` set) *and* `repoint_server` is `False`. Does the desired
   file's server URL end up in the payload in that case? Is that the
   behavior you'd want, or is this an edge case the guard doesn't actually
   cover?

Bring me what you find on both.

## Interview questions

**Q: Why does `deploy_vapi_tool.py` fetch the live resource before deciding
whether to update it, instead of just PATCHing the desired file straight
through?**
A: Two reasons. First, so I can print a real diff — "does the schema change,
does the server URL change" — instead of blindly telling the user "updating."
Second, so I can protect fields I don't want to touch, like the live server
URL, by copying them from what's actually live into the payload unless
someone explicitly opts into changing them.

**Q: What does `--apply` vs `--repoint-server` teach about designing a CLI
for a script that can hit a production API?**
A: Make the safe path the default and require an explicit flag to do anything
that writes. And when one of the writes is more dangerous than the others —
here, changing the webhook URL a live voice agent calls — require a second,
separate flag on top of the first one, so a single typo or a copy-pasted
command can't trigger it by accident.

**Q: Why does the code send a `User-Agent: curl/8.0` header instead of
letting `urllib` use its default?**
A: VAPI's edge/WAF rejects Python's default urllib User-Agent string with a
403, for reasons that aren't documented anywhere I could find — I only know
this because `export_config.py` failed with that exact error until the header
was added. It's a good example of a fix you can't derive from reading docs;
you have to reproduce the failure and read the actual response.

## Glossary added
`urllib.request` · WAF (web application firewall) · dry run · idempotent CLI
flag · BOM (byte-order mark) · `HTTPError` · schema diff (structural
comparison vs. raw equality)
