# Case study: a voice AI intake that never loses a lead

Portfolio rebuild of a system I delivered to a real client. The agency (Frontline CDL Staffing) is
fictional and all data is fictional. Facts and dates come from the work log in `tasks/todo.md`.

## The business problem

Truck drivers looking for work call staffing agencies at all hours. Recruiters work 9 to 5. A call
that nobody answers is often a driver who signs with the next agency. And when someone did take the
call, the details ended up in free text, so leads could not be sorted by urgency or by where the
driver lives.

## The outcome

A voice agent (VAPI) answers every call and asks the same questions every time. The answers land in
fixed fields: ZIP code, years of experience, and how soon the driver can start, turned into a
temperature (HOT within 3 days, MEDIUM 7, WARM 14, COLD later). The agent books a 15-minute recruiter
callback in Google Calendar at a free weekday time. Returning callers are recognised and get a
shorter script. Recruiters work from a dashboard ordered by who to call first, with the recording
and transcript one click away. The CRM (Zoho Recruit) gets each lead exactly once, even if it was
down when the driver called.

## The n8n and VAPI design

n8n is the glue: four small workflows for routing, intake, booking and the post-call report, so each
can be tested alone. Two VAPI assistants (new and returning callers) share one tool that saves the
details and books the callback.

One hard limit shaped the routing: VAPI drops a call if it does not learn which assistant to use
within 7.5 seconds. The routing workflow therefore asks our own database first (2 seconds), then
Zoho (4 seconds, no retries), and treats any failure as a new caller. A wrong guess costs a few
extra questions; a slow answer costs the whole call.

The agent judges, the code checks. The agent picks one of four fixed readiness answers and the code
maps it to a temperature; anything unexpected becomes UNKNOWN instead of quietly becoming COLD.

## Why Python, Postgres and an outbox worker were added

The first version wrote from n8n straight into Zoho during the call. Testing showed two problems:

- **The CRM was in the caller's path.** If Zoho was slow or down, the lead was at risk.
- **Two writers made duplicates.** On 2026-10-08 one test call produced two Zoho candidates one
  second apart: n8n and the new worker each wrote, and n8n's phone search never matched.

A third problem was in the voice script, not the backend: with the API stopped, n8n correctly
reported the save as failed, but the agent still said "your details are saved", because the prompt
said that unconditionally. The fix was to make the prompt follow the tool's answer.

The new rule: **save to our own database first, send to the CRM afterwards.** A FastAPI endpoint
saves the call, the applicant and a delivery slip (the **outbox row**) in one transaction. A
background worker sends pending rows to Zoho, waits longer after each failure (30 s, 60 s, 120 s, up
to 15 minutes), and is the only thing that writes to Zoho. It looks the candidate up by phone first,
so the lead arrives once. A repeated save of the same call is recognised and ignored, and incomplete
details are saved with a `needs_review` flag rather than dropped.

**The proof (2026-10-09).** I pointed the worker at a Zoho address that cannot answer and placed 2
real web calls. Both callers were told their details were saved and the callback booked, and that
was true: the database had them. Zoho received nothing. After restoring the address, both leads went
through on their own (after 5 and 6 tries): one candidate and one note each, no duplicates.

## Known gaps

- Webhook authentication between VAPI and n8n is paused. The first attempt broke inbound calls and
  was rolled back the same day; the cause is not confirmed.
- The recruiter emails (booked, moved, cancel request) are built but have not been seen arriving.
- From November 2026 British Columbia stays on UTC-7 while US Pacific moves to UTC-8, but the agent
  still says "Pacific". Drivers in the US would hear a time one hour off their local clock.
- Calendar events booked before 2026-10-27 have no phone tag, so a new booking does not replace them.
- The "cancel request" label comes from the AI's end-of-call analysis; its reliability is not measured.
- There is no cancel tool, on purpose: the agent offers to move the callback first and recruiters are
  emailed about a cancel request.

The full list, with what was and was not verified, is in the [README](../README.md).

## Who decided what

The business rules and scope were mine: database first, the temperature buckets, ZIP as its own
field, what "existing caller" means, one upcoming callback per phone, no cancel tool, and approval of
every live change. Claude Code wrote most of the code, tests and deploy scripts and ran the
simulated test calls.
