# Glossary

One line each. Say it out loud in your own words before moving on.

| Term | Meaning | First seen |
|---|---|---|
| **Webhook** | A URL that another system calls (HTTP POST) to tell you something happened. | U1 |
| **Tool call** | The voice AI deciding mid-conversation to call a function (`logApplicantInfo`) with arguments it collected. | U1 |
| **End-of-call report** | The message VAPI sends after hang-up, containing the transcript, summary, cost and structured data. It arrives for every call. | U1 |
| **Structured data** | Fields VAPI's analysis LLM extracts from the transcript into a JSON schema you define. | U1 |
| **Fail-open** | When a dependency fails, carry on with a safe default instead of blocking. For example, if Zoho is down, route the caller as new. | U1 |
| **E.164** | The international phone format `+<country><number>`, e.g. `+19185550142`. It gives one canonical spelling per phone. | U1 |
| **System of record** | The one place that's authoritative for some data. For candidates here, that's Zoho. | U1 |
| **Sub-workflow** | An n8n workflow called by another workflow instead of by a URL. | U1 |
| **Item** | One JSON object flowing between n8n nodes. | U2 |
| **Expression** | `{{ … }}` JavaScript inside an n8n node setting. | U2 |
| **`onError: continueRegularOutput`** | An n8n setting that passes an error along as data instead of stopping the run. | U2 |
| **IF node** | An n8n fork: reads one true/false value and sends the item down the true or false output. | U3 |
| **retryOnFail** | An n8n setting: if the call fails, try again automatically up to `maxTries` times. | U3 |
| **Timeout** | How long a call may take before it counts as failed. | U3 |
| **Upsert** | "Update or insert": update the record if it exists, otherwise create it. | U3 |
| **Guard node** | A node whose only job is to check something and stop (throw) if it is wrong. | U3 |
| **Tool-call ID** | The ID VAPI gives each tool call. The reply must echo it so VAPI knows which call the answer belongs to. | U3 |
| **Graceful fallback** | When something fails, give a safe, honest answer instead of an error. | U3 |
| **Idempotent** | Doing the same thing twice has the same effect as doing it once. | U4 |
| **Deterministic ID** | An ID computed from the input itself (e.g. the requested time), not generated randomly, so the same input always produces the same ID. | U4 |
| **Tombstone** | A deleted record whose ID still exists for a while in a "cancelled" state, instead of disappearing completely. | U4 |
| **ETag / `If-Match` (optimistic concurrency)** | A fingerprint of a record's current state. Attach it to a write with `If-Match`, and the server rejects the write if the record changed since you read it — a lock without needing a lock. | U4 |
| **`extendedProperties.private`** | Hidden metadata attached to a Google Calendar event, invisible in the UI but readable via the API. | U4 |
| **Outbox pattern** | Save the work item to your DB in the same transaction as the data, and let a worker send it to the external system later. | Plan |
| **`urllib.request`** | Python's built-in HTTP client — no install needed, unlike the `requests` library. | U6 |
| **WAF (web application firewall)** | A layer in front of an API that can reject requests before they reach the app, e.g. by `User-Agent` string. | U6 |
| **Dry run** | Show what a script would do without doing it — the default here, opt-in required to actually write. | U6 |
| **BOM (byte-order mark)** | An invisible marker some editors save at the start of a UTF-8 file; ignored by reading with `utf-8-sig`. | U6 |
| **`HTTPError`** | Python's exception for a 4xx/5xx response — distinct from a connection failure like DNS or timeout. | U6 |
| **Workflow-as-code** | Generating a system (here, n8n workflow JSON) from a reviewable script instead of building it by hand in a UI. | U7 |
| **Build artifact vs. source** | The generated file (workflow JSON) is a build artifact; the Python that produced it is the source. Edit the source, regenerate the artifact — never the reverse. | U7 |
| **Dependency-ordered deploy** | Deploying pieces in a specific order because a later piece needs an ID or value only the earlier piece's deploy produces. | U7 |
| **Dangling reference** | Code left pointing at something (here, an n8n node) that no longer exists after a refactor — fails silently until it runs. | U7 |
| **Syntax-check via subprocess** | Validating code written in language A from a test in language B by shelling out to language A's own interpreter, since B can't parse A itself. | U7 |
| **Smoke test (real call)** | A test that only proves anything by actually performing the real action (hitting a live, temporary webhook) — unlike a dry run, there's no "would do" version of it. | U8 |
| **OAuth proxy (via n8n)** | Routing an API call through an existing authenticated system (n8n's saved credential) instead of implementing OAuth token refresh yourself. | U8 |
| **Pinned fixture vs. disposable test data** | A reusable, permanently-labelled test record you clean only the byproducts of, versus throwaway data deleted along with everything that touched it. | U8 |
| **Naive vs. timezone-aware datetime** | A naive `datetime` has no UTC-offset information attached; an aware one does — sending a naive local timestamp over a webhook silently assumes the receiver guesses the right timezone. | U8 |
| **Transaction (atomic write)** | A group of database writes that either all commit or all roll back — no half-saved state. | A1 |
| **Rollback** | Undoing every write in the current transaction after an error. | A1 |
| **Migration** | A versioned `.sql` file that changes the schema; a runner applies each file once, in order. | A1 |
| **UNIQUE constraint / foreign key** | UNIQUE: the database refuses duplicate values in a column. Foreign key: a column must point at a row that exists in another table. | A1 |
| **jsonb** | Postgres column type storing JSON in a queryable binary form; used to keep the raw VAPI payload. | A1 |
| **Autocommit** | Each statement commits immediately on its own, so there is no multi-statement transaction to roll back. | A1 |
| **Idempotent** | Doing the same request twice has the same effect as doing it once; lets a sender safely retry. | A2 |
| **Replay / redelivery** | The same request arriving again, usually because the sender never got our reply. | A2 |
| **Upsert (`ON CONFLICT`)** | One statement that inserts a row, or updates the existing one if the key already exists; the database is the single judge, so no race between "check" and "insert". | A2 |
| **`COALESCE(NULLIF(new,''), old)`** | "Use the new value if it was provided, otherwise keep the old one." | A2 |
| **Flag for review (`needs_review`)** | Saving imperfect data with a marker for a human to fix, instead of rejecting it and losing the lead. | A2 |
| **Endpoint** | One address of our API that does one job, e.g. `GET /api/calls` lists calls. | C1 |
| **Session cookie** | A small signed ticket the website gives your browser after login; the browser shows it on every request so you do not log in again. | C1a |
| **Hash (password hash)** | A one-way scramble of a password. We store the scramble, never the password, and cannot turn it back. | C1a |
| **Salt** | Random extra text mixed into a password before scrambling, so two people with the same password get different hashes. | C1a |
| **`session_version`** | A number on each user. Changing the password raises it, which makes every ticket handed out earlier stop working, so everyone is logged out at once. | C1a |
| **Role** | What a logged-in person is allowed to do: `recruiter` (review and correct) or `admin` (the owner). | C1a |
| **401 / 403 / 404 / 409 / 422** | HTTP answers: 401 "log in first", 403 "logged in but not allowed", 404 "not found", 409 "conflict with existing data", 422 "your input is invalid". | C1a to C1c |
| **Pagination (`limit` / `offset`)** | Asking for a list in pages: `limit` = page size, `offset` = how many to skip. | C1b |
| **Outbox** | A table of "delivery slips": jobs saved in our database that still have to reach Zoho. | B1 |
| **Worker** | A program that runs all the time, picks up pending slips from the outbox, and delivers them to Zoho. | B1 |
| **Backoff** | Waiting longer after each failed try (30s, 60s, 120s...) so we do not hammer a service that is down. | B1 |
| **Audit log** | A permanent record of who changed what and when, with old and new values. | C1c |
| **Fallback** | The plan B when the first approach fails: if the saved Zoho id is gone, search by phone instead. | C1c |
| **Mutation test** | Deliberately breaking the code to check that a test notices. If no test fails, the tests are too weak. | A1 to C1 |
| **Constraint (CHECK)** | A rule the database itself enforces, e.g. "a correction row must point at an audit row". | C1c |
| **Docker / container** | A program that runs other programs in sealed boxes (containers). Each box holds the program and everything it needs, so it works the same on your PC and on a server. | C1 |
| **Test database** | A throwaway database used only by tests. It may be wiped at any time, so it must never be the real one. | C1 |
| **Development / staging / production** | Three places a system runs: your own machine (break things freely), a copy of the real setup for a final check, and the real one that customers use. Only production holds real data. | C1 |
| **CI (continuous integration)** | A robot that runs all the tests automatically every time the code changes, in disposable containers, before anything goes live. | C1 |
| **Deploy** | Putting new code on the real server and restarting it, so the live system runs the new version. | C3 |
| **Migration** | A numbered database change (new table or column) run once, in order. Writing the file changes nothing; running it does. | C1 to C3 |
| **Rollback** | Going back to the previous working version. It restores code, not database changes already made. | C3 |
| **Port** | A numbered door on a server. The number says which program should get the message (80 and 443: Caddy, 8000: our API). | C3 |
| **Reverse proxy (Caddy)** | The front door of a server: it receives requests from the internet and passes them to the right program inside. | C3 |
| **DNS record (A record)** | One line in the internet's phone book: this name goes to that IP address. | C3 |
| **TLS / HTTPS certificate** | Proof the site is really yours, which also encrypts the connection. Caddy gets it for free from Let's Encrypt. | C3 |
| **Health check (/healthz)** | A tiny page that only proves the program is running, so Docker can tell if the container is healthy. | C3 |
| **Rate limit (throttle, 429)** | A speed limit on tries, such as wrong passwords. Past the limit the answer is 429, too many requests. | C3 |
| **CSP (Content-Security-Policy)** | A rule sent to the browser listing what a page may load, so a hacked or wrong file cannot run. | C3 |
| **Round trip / latency** | A round trip is one message out and one answer back. Latency is the waiting caused by distance and setup, not by heavy work. | C2 speed |
| **Connection pool** | A few database connections kept open and lent out to requests, so nobody pays about 250 ms to open a new one. | C2 speed |
| **Optimistic update** | Showing the expected result on screen at once and fixing it only if the server says no. | C2 speed |
| **Independent review** | A check by someone who did not write the code, so they do not share its blind spots. | C3 |
| **Workflow (n8n)** | One chain of steps in n8n: receive something, process it, send it on. | C1e n8n hop |
| **Side branch** | A second path off the same step, so a new job runs next to the main flow and a failure in one does not stop the other. | C1e n8n hop |
| **Backup (before a change)** | A copy made before editing, so a mistake can be undone by switching back. | C1e n8n hop |
| **Internal hostname** | A name that only works inside the same network (like `cdl-api`), so a service is never called through the public internet. | C1e n8n hop |
| **Header Auth credential** | An API key saved once in n8n and attached automatically to each call as a header. | C1e n8n hop |
| **Retry / timeout / max tries** | Try again after a pause; stop waiting after a set time; max tries counts the first attempt too. | C1e n8n hop |
| **Idempotent** | Doing the same call twice has the same result as doing it once, which is what makes a retry safe. | C1e n8n hop |
| **Blip vs outage** | A blip is a short glitch a retry can fix. An outage is long and needs a queue (like the outbox). | C1e n8n hop |
| **Draft vs published (n8n)** | In this n8n, Save stores a draft only. The live workflow keeps running the last published version until you press Publish. | C1e n8n hop |
| **Design tokens** | Named values for colors, sizes and spacing (like `--accent`), set once and reused everywhere, so one change restyles the whole app. | UI redesign |
| **Type scale** | A short, fixed list of text sizes (here 12 to 28px) that every screen picks from, instead of a new size per element. | UI redesign |
| **SVG sprite** | One hidden block of icon drawings in the page; each icon on screen just points to one of them by name. | UI redesign |
| **Reduced motion** | An operating-system setting for people who get dizzy from animation; the app turns its movement off when it is on. | UI redesign |
| **Enum (fixed answers)** | A list of the only allowed answers, like a multiple-choice question. The voice agent must pick one, so the code never has to guess from free text. | Readiness categories |
| **Tool mock** | A fake reply put in place of a real tool during a test, so no real record or booking is made. | Simulated calls |
| **Simulation** | A test where an AI plays the caller and talks to the agent, so you can try many calls without phoning anyone. | Simulated calls |
| **PATCH** | A request that changes part of a saved object. Anything you leave out may be deleted, so you send what must stay and check the whole object afterwards. | VAPI tool update |
| **Regression** | Something that worked before breaks after a change. Losing the tool's webhook address was one. | VAPI tool update |
| **Drift** | The live system no longer matches the saved source, usually after a hand edit. The check before deploy found it in Normalize Intake. | n8n code swap |
