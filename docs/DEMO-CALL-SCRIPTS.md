# Demo call scripts (C4 step 2b)

Two real calls to the live agent, recorded by VAPI. One shows the happy path, one shows the "needs a closer look"
path. Everything you say is fictional. Total cost: 2 real calls, about 3 minutes, 2 rows in the real database,
1 candidate in your Zoho (the second call creates none).

## Before you dial (check all four)

1. **Use a phone number the agent has never seen.** The agent looks the caller up by number. A number that already has a
   candidate (your earlier test calls) is routed to the "existing lead" agent, which greets you by name and skips the
   intake. Use a different phone, or confirm your number is not in Zoho.
2. **Call on a weekday, any hour.** The agent only accepts callback times Monday to Friday, 9 AM to 5 PM Pacific. If
   you call Friday after 5 PM, ask for "Monday" instead of "tomorrow".
3. **Quiet room, normal speed, one answer at a time.** The recording goes on the demo site. Wait for the agent to finish.
4. **Never say your real name, number or city.** The agent reads the callback number back out loud, so say only the
   fictional one. Your real phone shows up only in VAPI's call log, never in the recording.

## Call 1: new driver, happy path (about 2 minutes)

Persona: **Carlos Rivera**, Fresno, California, 93706. 6 years, dry van. Ready in about a week. Callback number
**559-555-0127**. This is the full intake, plus one question the agent must not answer (pay), which shows it does not make
things up.

| Agent says (about) | You say |
|---|---|
| "Thanks for calling Frontline CDL Staffing... this call is recorded... Are you calling about a driving job today?" | "Yeah, hi. I saw you guys were looking for drivers." |
| "Awesome, I can help with that... First, what's your full name?" | "Carlos Rivera." |
| "What city and state are you in, and what's your ZIP code?" | "Fresno, California. Nine three seven oh six." |
| reads the ZIP back | "That's right." |
| "How much tractor-trailer experience do you have?" | "A little over six years, mostly dry van." |
| confirms what it heard | "Yep." |
| *(optional, here or later)* | **"Before I go on, what does it pay?"** |
| "I don't have those details on hand, but the recruiter will walk you through pay..." | "Okay, fair enough." |
| "How soon are you ready to start... three days, seven days, fourteen days, or later?" | "About a week, so seven days." |
| "What's the best phone number for a senior recruiter to call you on?" | "Five five nine, five five five, oh one two seven." |
| reads it back | "Yes, that's it." |
| "What would be a good time for a senior recruiter to call you?" | "Tomorrow afternoon, around two." |
| "Would two or three work better for you?" | "Two is good." |
| "Let me save that for you." ... confirms the booking | "Great, thanks." |
| "Is there anything else I can help you with today?" | "No, that's all." |
| "Thank you for calling Frontline CDL Staffing..." | *(hang up after it ends the call)* |

What the demo viewer sees after this: a new applicant "Carlos Rivera" in Fresno, CA, readiness 7 days (Medium), a
callback request, a summary, a transcript and a playable recording.

## Call 2: no new call needed (decided 2026-10-22)

After call 1 the caller's number is a known lead (Carlos Rivera), so a second call from the same phone goes to the
"existing lead" agent, which greets by name. A clean "new caller who is not a driver" call is no longer possible without a
second phone. The first attempt (live call id 10, 12:42 PM) is a better sample anyway: the caller hung up after three lines,
before giving a name. It shows what the recruiter sees when a call ends early: flagged "Needs a closer look", the
reason ("the call ended before the agent saved any details"), a summary, a transcript and a recording.

So the two samples are:
1. Call id 11: Carlos Rivera, the full intake (happy path).
2. Call id 10: the caller who hung up early (the "needs review" path).

Live call id 12 is empty (no transcript, no summary) and is not used; it can be deleted.

## After the calls

1. Pick the recordings: calls 10 and 11. They are in the VAPI dashboard, or I can fetch them with a read-only API call if you say so.
2. I pull the two transcripts (read-only), copy their wording into the demo seed so the text matches the audio, and wire the
   files in (`DEMO_RECORDINGS_DIR`, outside git).
3. The two real rows stay in the real database (they are the real-dashboard walkthrough data). Carlos Rivera is also a real Zoho candidate.
