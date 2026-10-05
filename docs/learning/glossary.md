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
