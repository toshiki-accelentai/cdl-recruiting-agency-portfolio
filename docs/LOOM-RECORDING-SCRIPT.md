# CDL recruiting automation Loom script

## Target length

Aim for **3 minutes 30 seconds** and never exceed **4 minutes**.

Record one new-applicant call on camera. Prove the existing-applicant scenario
with a short routing execution and call-log walkthrough instead of replaying a
second full conversation.

## Confidentiality rule

Present this as a portfolio-safe rebuild based on a system delivered to a real
client. The demonstration uses fictional candidate data and excludes the
original implementation and proprietary details.

Do not discuss the project's provenance or expose confidential workflows,
business names, or production data.

## Before recording

- Rehearse once off camera and confirm the VAPI call, n8n execution, Zoho
  Candidate, Google Calendar event, and related Notes.
- After the rehearsal creates the Candidate, place one brief second call from
  the same number so an existing-applicant routing execution is ready to show.
- Prepare four tabs: n8n workflows, Zoho Candidate, Google Calendar, and VAPI
  call log.
- Hide credentials, API keys, OAuth screens, and unrelated records.
- Use a genuinely free weekday callback slot between 9 AM and 5 PM Pacific.

## Fictional demo profile

- Name: Daniel Carter
- Location: Tacoma, Washington 98402
- Experience: a little over five years
- Readiness: within three days
- Phone: the number placing the call

## 0:00–0:15 — Opening

Show the four n8n workflows.

> Hi, I'm Toshiki. This is a portfolio demonstration of an AI-assisted
> recruiting workflow, rebuilt from a system I delivered to a real client. To
> protect confidentiality, this version uses fictional data and excludes the
> client's proprietary details. It handles after-hours candidate intake and
> recruiter callback scheduling.

## 0:15–0:35 — Architecture

Keep the workflow list visible. Do not open individual credentials or node
settings.

> VAPI handles the conversation, n8n orchestrates the process, Zoho Recruit is
> the system of record, and Google Calendar manages callbacks. I separated
> routing, intake, booking, and post-call reporting so each part can be tested
> and debugged independently.

## 0:35–2:05 — New-applicant call

Start the call and read only the caller lines. Wait for the assistant after
each answer.

**Opening**

> Hi, I'm calling because I'm interested in a CDL driving job.

**Name**

> My name is Daniel Carter.

**Location**

> I'm in Tacoma, Washington. My ZIP code is nine eight four zero two.

**ZIP confirmation**

> Yes, that's correct.

**Experience**

> I have a little over five years of tractor-trailer experience.

**Readiness**

> I'm ready to start within the next three days.

**Phone**

> The best number is the number I'm calling from.

If the assistant asks for the digits, read the real number slowly. Confirm it
with:

> Yes, that's right.

**Callback time**

> Tuesday, [date], at ten thirty A M would work for me.

Replace `[date]` with the verified future date.

**Close**

> No, that's everything. Thank you.

## 2:05–2:50 — Show the result

Move quickly through the Zoho Candidate, Calendar event, and related Notes.

> The call created a structured Candidate with the name, phone, location,
> exact experience, and readiness captured in dedicated fields. The ZIP code
> is available for downstream geographic sourcing rather than being buried in
> a transcript.
>
> Before confirming the callback, the workflow checked availability, created
> a fifteen-minute Calendar event, and verified that the saved event belonged
> to this call. The intake and post-call context are attached to the Candidate
> as related Notes.

Pause briefly on **Experience in Years = 5** so the spoken answer and Zoho
value are visibly consistent.

## 2:50–3:15 — Existing-applicant scenario

Show the prepared routing execution from the brief second call. Do not replay
the whole call.

> On the next call from the same number, the routing workflow normalized the
> phone number, found Daniel in Zoho Recruit, and selected the returning-caller
> assistant. This avoids repeating the full first-time intake and gives the
> caller a more relevant path.

## 3:15–3:35 — Close

Return to the workflow list.

> The result is a maintainable automation with structured CRM data, verified
> scheduling, isolated failure boundaries, retries, and automated tests. It
> demonstrates how I turn a manual business process into a reliable workflow.
> Thank you for watching.

## Recording rule

If the live call fails, stop the recording, fix the cause, and start a clean
take. Do not troubleshoot or repeatedly retry on camera.
