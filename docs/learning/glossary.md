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
| **Outbox pattern** | Save the work item to your DB in the same transaction as the data, and let a worker send it to the external system later. | Plan |
