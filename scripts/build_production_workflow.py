#!/usr/bin/env python3
"""Generate the canonical CDL n8n workflow from reviewable source.

This script only writes local JSON. It never calls n8n, VAPI, Zoho, or Google.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
HELPERS = (ROOT / "workflow-src" / "cdl_helpers.js").read_text(encoding="utf-8")
OUT = ROOT / "config" / "n8n" / "production" / "cdl-intake-production.json"

ZOHO_CREDENTIAL = {"id": "ur8ddSQIeUDGrce8", "name": "Zoho Recruit OAuth"}
GOOGLE_CREDENTIAL = {
    "id": "1sf9UUIeS6G5wyhc",
    "name": "Google Calendar account",
}
CALENDAR_ID = "toshiki@accelentai.com"
NEW_ASSISTANT_ID = "6901a714-a6c5-45a2-9395-455e09e0051b"
EXISTING_ASSISTANT_ID = "542bae1c-51b5-4d83-a3fe-446836b4801d"


def stable_id(label: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"frontline-cdl:{label}"))


def node(name: str, kind: str, parameters: dict, x: int, y: int, version=1, **extra) -> dict:
    return {
        "parameters": parameters,
        "id": stable_id(f"node:{name}"),
        "name": name,
        "type": kind,
        "typeVersion": version,
        "position": [x, y],
        **extra,
    }


def webhook(name: str, path: str, x: int, y: int, response_mode="responseNode") -> dict:
    return node(
        name,
        "n8n-nodes-base.webhook",
        {"httpMethod": "POST", "path": path, "responseMode": response_mode, "options": {}},
        x,
        y,
        2.1,
        webhookId=stable_id(f"webhook:{path}"),
    )


def code(name: str, adapter: str, x: int, y: int, helpers=True) -> dict:
    source = f"{HELPERS}\n\n{adapter}" if helpers else adapter
    return node(name, "n8n-nodes-base.code", {"jsCode": source}, x, y, 2)


def zoho_request(name: str, parameters: dict, x: int, y: int) -> dict:
    return node(
        name,
        "n8n-nodes-base.httpRequest",
        {
            **parameters,
            "authentication": "genericCredentialType",
            "genericAuthType": "oAuth2Api",
            "options": {"timeout": 10000},
        },
        x,
        y,
        4.4,
        credentials={"oAuth2Api": ZOHO_CREDENTIAL},
        retryOnFail=True,
        maxTries=3,
        waitBetweenTries=1000,
        onError="continueRegularOutput",
        alwaysOutputData=True,
    )


def google_request(name: str, parameters: dict, x: int, y: int) -> dict:
    return node(
        name,
        "n8n-nodes-base.httpRequest",
        {
            **parameters,
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "googleCalendarOAuth2Api",
            "options": {"timeout": 10000},
        },
        x,
        y,
        4.4,
        credentials={"googleCalendarOAuth2Api": GOOGLE_CREDENTIAL},
        retryOnFail=True,
        maxTries=3,
        waitBetweenTries=1000,
        onError="continueRegularOutput",
        alwaysOutputData=True,
    )


def condition(name: str, expression: str, x: int, y: int) -> dict:
    return node(
        name,
        "n8n-nodes-base.if",
        {
            "conditions": {
                "options": {"caseSensitive": True, "typeValidation": "strict", "version": 2},
                "conditions": [{
                    "id": stable_id(f"condition:{name}"),
                    "leftValue": expression,
                    "rightValue": "",
                    "operator": {"type": "boolean", "operation": "true", "singleValue": True},
                }],
                "combinator": "and",
            },
            "options": {},
        },
        x,
        y,
        2.2,
    )


def respond(name: str, body_expression: str, x: int, y: int, response_code=200) -> dict:
    return node(
        name,
        "n8n-nodes-base.respondToWebhook",
        {
            "respondWith": "json",
            "responseBody": body_expression,
            "options": {
                "responseCode": response_code,
                "responseHeaders": {"entries": [{"name": "Content-Type", "value": "application/json"}]},
            },
        },
        x,
        y,
        1.4,
    )


def connect(connections: dict, source: str, target: str, output=0) -> None:
    entry = connections.setdefault(source, {"main": []})
    while len(entry["main"]) <= output:
        entry["main"].append([])
    entry["main"][output].append({"node": target, "type": "main", "index": 0})


def build() -> dict:
    nodes: list[dict] = []
    connections: dict = {}

    # Fast caller routing. Zoho failure intentionally falls back to the new-lead assistant.
    nodes += [
        webhook("Route Caller Webhook", "cdl/assistant-request", 0, -600),
        code("Normalize Route Request", """
const message = $json.body?.message ?? $json.message ?? {};
const phone = normalizePhone(message.call?.customer?.number ?? message.customer?.number ?? '');
return [{ json: { phone, valid: Boolean(phone) } }];
""", 240, -600),
        zoho_request("Find Candidate for Routing", {
            "method": "GET",
            "url": "https://recruit.zoho.com/recruit/v2/Candidates/search",
            "sendQuery": True,
            "queryParameters": {"parameters": [
                {"name": "phone", "value": "={{ $('Normalize Route Request').first().json.phone || '+10000000000' }}"},
                {"name": "per_page", "value": "1"},
            ]},
        }, 500, -600),
        code("Build Assistant Response", f"""
const route = $('Normalize Route Request').first().json;
const candidate = Array.isArray($json.data) ? $json.data[0] : null;
const existing = Boolean(route.valid && candidate?.id);
return [{{ json: {{
  assistantId: existing ? '{EXISTING_ASSISTANT_ID}' : '{NEW_ASSISTANT_ID}',
  assistantOverrides: {{ variableValues: {{
    phoneNumber: route.phone ?? '',
    name: existing ? [candidate.First_Name, candidate.Last_Name].filter(Boolean).join(' ') : '',
  }} }},
  routing: existing ? 'existing_candidate' : 'new_candidate',
}} }}];
""", 760, -600, helpers=False),
        respond("Respond Route", "={{ $json }}", 1020, -600),
    ]
    connect(connections, "Route Caller Webhook", "Normalize Route Request")
    connect(connections, "Normalize Route Request", "Find Candidate for Routing")
    connect(connections, "Find Candidate for Routing", "Build Assistant Response")
    connect(connections, "Build Assistant Response", "Respond Route")

    # Applicant intake and deterministic classification/booking.
    nodes += [
        webhook("Applicant Intake Webhook", "cdl/log-applicant", 0, 0),
        code("Normalize Intake", """
const message = $json.body?.message ?? {};
const toolCall = message.toolCalls?.[0];
const args = toolCall?.function?.arguments ?? {};
const callId = message.call?.id ?? $json.headers?.['x-call-id'] ?? '';
const phone = normalizePhone(args.phoneNumber ?? message.call?.customer?.number ?? '');
const names = splitName(args.name);
const location = parseLocation(args);
const errors = [];
if (!toolCall?.id) errors.push('missing_tool_call_id');
if (!callId) errors.push('missing_call_id');
if (!phone) errors.push('invalid_phone');
if (!names.lastName || names.lastName === 'Unknown') errors.push('missing_name');
if (!location.city) errors.push('missing_city');
if (!location.state) errors.push('missing_state');
if (!location.zipCode) errors.push('missing_zip_code');
if (!args.preferredCallbackTime) errors.push('missing_callback_time');
return [{ json: {
  valid: errors.length === 0, validationErrors: errors,
  toolCallId: toolCall?.id ?? '', callId, phone,
  firstName: names.firstName, lastName: names.lastName,
  ...location,
  experienceText: clean(args.experience),
  experienceYears: parseExperienceYears(args.experience),
  readiness: clean(args.readiness),
  temperature: classifyTemperature(args.readiness),
  preferredCallbackTime: clean(args.preferredCallbackTime),
} }];
""", 240, 0),
        condition("Intake Valid?", "={{ $json.valid }}", 500, 0),
        respond(
            "Respond Invalid Intake",
            "={{ {results:[{toolCallId:$json.toolCallId || '',result:JSON.stringify({status:'invalid_request',saved:false,booked:false,message:'I need to confirm a few details before submitting your application.',missing:$json.validationErrors})}]} }}",
            760,
            220,
        ),
        zoho_request("Find Candidate for Intake", {
            "method": "GET",
            "url": "https://recruit.zoho.com/recruit/v2/Candidates/search",
            "sendQuery": True,
            "queryParameters": {"parameters": [
                {"name": "phone", "value": "={{ $('Normalize Intake').first().json.phone }}"},
                {"name": "per_page", "value": "1"},
            ]},
        }, 760, -40),
        code("Build Candidate Write Request", """
const intake = $('Normalize Intake').first().json;
const existing = Array.isArray($json.data) ? $json.data[0] : null;
const candidate = {
  Last_Name: intake.lastName,
  Phone: intake.phone,
  City: intake.city,
  State: intake.state,
  Zip_Code: intake.zipCode,
  Experience_in_Years: intake.experienceYears,
  Source: 'Phone Call',
};
if (intake.firstName) candidate.First_Name = intake.firstName;
return [{ json: {
  ...intake,
  existingId: existing?.id ?? null,
  method: existing?.id ? 'PUT' : 'POST',
  url: existing?.id
    ? `https://recruit.zoho.com/recruit/v2/Candidates/${existing.id}`
    : 'https://recruit.zoho.com/recruit/v2/Candidates',
  body: { data: [candidate], trigger: [] },
} }];
""", 1020, -40, helpers=False),
        zoho_request("Write Candidate", {
            "method": "={{ $json.method }}",
            "url": "={{ $json.url }}",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify($json.body) }}",
        }, 1280, -40),
        code("Resolve Candidate Result", """
const request = $('Build Candidate Write Request').first().json;
const record = Array.isArray($json.data) ? $json.data[0] : null;
const apiSuccess = record?.code === 'SUCCESS' || record?.status === 'success';
const candidateId = request.existingId ?? record?.details?.id ?? null;
const candidateSaved = Boolean(candidateId && apiSuccess);
const note = [
  `VAPI Call ID: ${request.callId}`,
  `Phone: ${request.phone}`,
  `Location: ${request.city}, ${request.state} ${request.zipCode}`,
  `Experience: ${request.experienceText} (${request.experienceYears} years normalized)`,
  `Readiness: ${request.readiness}`,
  `Temperature: ${request.temperature}`,
  `Requested callback: ${request.preferredCallbackTime}`,
].join('\\n');
return [{ json: {
  ...request, candidateId, candidateSaved,
  candidateError: candidateSaved ? null : ($json.message ?? $json.error?.message ?? record?.message ?? 'candidate_write_failed'),
  intakeNoteBody: { data: [{ Note_Title: `VAPI Intake — ${request.callId}`, Note_Content: note, Parent_Id: candidateId, se_module: 'Candidates' }] },
} }];
""", 1540, -40, helpers=False),
        condition("Candidate Saved?", "={{ $json.candidateSaved }}", 1800, -40),
        respond(
            "Respond Candidate Failure",
            "={{ {results:[{toolCallId:$json.toolCallId,result:JSON.stringify({status:'manual_followup',saved:false,booked:false,message:'I could not complete the automatic submission. A recruiter will need to follow up manually.',callId:$json.callId})}]} }}",
            2060,
            180,
        ),
        zoho_request("Add Intake Note", {
            "method": "POST",
            "url": "https://recruit.zoho.com/recruit/v2/Notes",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify($json.intakeNoteBody) }}",
        }, 2060, -80),
        code("Validate Callback", """
const intake = $('Resolve Candidate Result').first().json;
const callback = validateCallback(intake.preferredCallbackTime, new Date());
const slotSeconds = callback.startUtc ? Math.floor(new Date(callback.startUtc).getTime() / 1000) : 0;
const eventId = `cdlslot${slotSeconds.toString(32)}`;
return [{ json: { ...intake, ...callback, eventId, callbackValid: callback.valid } }];
""", 2320, -80),
        condition("Callback Valid?", "={{ $json.callbackValid }}", 2580, -80),
        code("Build Non-Booking Result", """
return [{ json: {
  ...$json,
  status: 'slot_unavailable', booked: false, calendarUrl: '', bookingReason: $json.reason,
  callerMessage: 'That time is outside our callback hours. Please choose another weekday between 9 AM and 5 PM Pacific.',
} }];
""", 2840, 140, helpers=False),
        google_request("Check Calendar Availability", {
            "method": "POST",
            "url": "https://www.googleapis.com/calendar/v3/freeBusy",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify({timeMin:$json.startUtc,timeMax:$json.endUtc,timeZone:'America/Vancouver',items:[{id:'" + CALENDAR_ID + "'}]}) }}",
        }, 2840, -120),
        code("Assess Availability", """
const callback = $('Validate Callback').first().json;
const response = $input.first().json;
const calendar = response.calendars?.['toshiki@accelentai.com'];
const calendarError = Boolean(response.error || !calendar || calendar.errors?.length);
const conflicts = calendar?.busy ?? [];
return [{ json: {
  ...callback,
  calendarAvailable: !calendarError && conflicts.length === 0,
  bookingReason: calendarError ? 'calendar_error' : (conflicts.length ? 'slot_unavailable' : 'available'),
} }];
""", 3100, -120, helpers=False),
        condition("Calendar Slot Free?", "={{ $json.calendarAvailable }}", 3360, -120),
        code("Build Calendar Event", """
return [{ json: {
  ...$json,
  eventBody: {
    id: $json.eventId,
    summary: `${$json.temperature} - CDL Candidate Callback - ${[$json.firstName, $json.lastName].filter(Boolean).join(' ')}`,
    description: `VAPI Call ID: ${$json.callId}\nCandidate phone: ${$json.phone}\nZoho Candidate ID: ${$json.candidateId}`,
    start: { dateTime: $json.startUtc, timeZone: 'America/Vancouver' },
    end: { dateTime: $json.endUtc, timeZone: 'America/Vancouver' },
    transparency: 'opaque',
    reminders: { useDefault: true },
    extendedProperties: { private: { vapiCallId: $json.callId, zohoCandidateId: $json.candidateId } },
  },
} }];
""", 3620, -180, helpers=False),
        google_request("Create Calendar Event", {
            "method": "POST",
            "url": "https://www.googleapis.com/calendar/v3/calendars/toshiki%40accelentai.com/events",
            "sendQuery": True,
            "queryParameters": {"parameters": [{"name": "sendUpdates", "value": "none"}]},
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify($json.eventBody) }}",
        }, 3880, -180),
        google_request("Confirm Calendar Event", {
            "method": "GET",
            "url": "=https://www.googleapis.com/calendar/v3/calendars/toshiki%40accelentai.com/events/{{ $('Assess Availability').first().json.eventId }}",
        }, 4140, -180),
        condition("Calendar Event Cancelled?", "={{ $json.status === 'cancelled' && Boolean($json.etag) }}", 4400, -180),
        google_request("Restore Cancelled Slot", {
            "method": "PUT",
            "url": "=https://www.googleapis.com/calendar/v3/calendars/toshiki%40accelentai.com/events/{{ $('Assess Availability').first().json.eventId }}",
            "sendQuery": True,
            "queryParameters": {"parameters": [{"name": "sendUpdates", "value": "none"}]},
            "sendHeaders": True,
            "headerParameters": {"parameters": [{
                "name": "If-Match",
                "value": "={{ $('Confirm Calendar Event').first().json.etag }}",
            }]},
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify({...$('Build Calendar Event').first().json.eventBody,status:'confirmed'}) }}",
        }, 4660, -260),
        google_request("Confirm Restored Slot", {
            "method": "GET",
            "url": "=https://www.googleapis.com/calendar/v3/calendars/toshiki%40accelentai.com/events/{{ $('Assess Availability').first().json.eventId }}",
        }, 4920, -260),
        code("Build Booked Result", """
const context = $('Assess Availability').first().json;
const eventMatches = Boolean(!$json.error && $json.id === context.eventId && $json.status !== 'cancelled');
const eventOwner = $json.extendedProperties?.private?.vapiCallId;
const ownedByCall = eventMatches && eventOwner === context.callId;
const slotUnavailable = context.bookingReason === 'slot_unavailable' || (eventMatches && !ownedByCall);
return [{ json: {
  ...context,
  status: ownedByCall ? 'booked' : (slotUnavailable ? 'slot_unavailable' : 'manual_followup'),
  booked: ownedByCall,
  calendarUrl: ownedByCall ? ($json.htmlLink ?? '') : '',
  calendarEventId: ownedByCall ? ($json.id ?? '') : '',
  bookingReason: ownedByCall ? 'booked' : (slotUnavailable ? 'slot_race_lost' : 'calendar_create_failed'),
  callerMessage: ownedByCall
    ? `Your recruiter callback is confirmed for ${context.preferredCallbackTime}.`
    : (slotUnavailable
      ? 'That callback time is already taken. Please choose another time.'
      : 'Your application was saved, but the calendar could not be confirmed. A recruiter will follow up manually.'),
} }];
""", 5180, -180, helpers=False),
        code("Build Unavailable Result", """
return [{ json: {
  ...$json,
  status: $json.bookingReason === 'calendar_error' ? 'manual_followup' : 'slot_unavailable',
  booked: false, calendarUrl: '', calendarEventId: '',
  callerMessage: $json.bookingReason === 'calendar_error'
    ? 'Your application was saved, but the calendar could not be confirmed. A recruiter will follow up manually.'
    : 'That callback time is already taken. Please choose another time.',
} }];
""", 3620, 20, helpers=False),
        respond(
            "Respond Booking Result",
            "={{ {results:[{toolCallId:$json.toolCallId,result:JSON.stringify({status:$json.status,saved:true,booked:$json.booked,confirmedTime:$json.booked?$json.preferredCallbackTime:null,calendarUrl:$json.calendarUrl,message:$json.callerMessage,callId:$json.callId,candidateId:$json.candidateId})}]} }}",
            4140,
            -80,
        ),
        zoho_request("Add Booking Note", {
            "method": "POST",
            "url": "https://recruit.zoho.com/recruit/v2/Notes",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify({data:[{Note_Title:'Callback — '+$json.callId,Note_Content:['Status: '+$json.status,'Reason: '+$json.bookingReason,'Requested: '+$json.preferredCallbackTime,'Confirmed: '+($json.booked?$json.preferredCallbackTime:'not booked'),'Calendar URL: '+($json.calendarUrl||'none')].join('\\n'),Parent_Id:$json.candidateId,se_module:'Candidates'}]}) }}",
        }, 4400, -80),
    ]
    connect(connections, "Applicant Intake Webhook", "Normalize Intake")
    connect(connections, "Normalize Intake", "Intake Valid?")
    connect(connections, "Intake Valid?", "Find Candidate for Intake", 0)
    connect(connections, "Intake Valid?", "Respond Invalid Intake", 1)
    connect(connections, "Find Candidate for Intake", "Build Candidate Write Request")
    connect(connections, "Build Candidate Write Request", "Write Candidate")
    connect(connections, "Write Candidate", "Resolve Candidate Result")
    connect(connections, "Resolve Candidate Result", "Candidate Saved?")
    connect(connections, "Candidate Saved?", "Add Intake Note", 0)
    connect(connections, "Candidate Saved?", "Respond Candidate Failure", 1)
    connect(connections, "Add Intake Note", "Validate Callback")
    connect(connections, "Validate Callback", "Callback Valid?")
    connect(connections, "Callback Valid?", "Check Calendar Availability", 0)
    connect(connections, "Callback Valid?", "Build Non-Booking Result", 1)
    connect(connections, "Check Calendar Availability", "Assess Availability")
    connect(connections, "Assess Availability", "Calendar Slot Free?")
    connect(connections, "Calendar Slot Free?", "Build Calendar Event", 0)
    connect(connections, "Calendar Slot Free?", "Confirm Calendar Event", 1)
    connect(connections, "Build Calendar Event", "Create Calendar Event")
    connect(connections, "Create Calendar Event", "Confirm Calendar Event")
    connect(connections, "Confirm Calendar Event", "Calendar Event Cancelled?")
    connect(connections, "Calendar Event Cancelled?", "Restore Cancelled Slot", 0)
    connect(connections, "Calendar Event Cancelled?", "Build Booked Result", 1)
    connect(connections, "Restore Cancelled Slot", "Confirm Restored Slot")
    connect(connections, "Confirm Restored Slot", "Build Booked Result")
    connect(connections, "Build Booked Result", "Respond Booking Result")
    connect(connections, "Build Unavailable Result", "Respond Booking Result")
    connect(connections, "Build Non-Booking Result", "Respond Booking Result")
    connect(connections, "Respond Booking Result", "Add Booking Note")

    # Acknowledge post-call events immediately, then persist transcript/metadata as a Zoho note.
    nodes += [
        webhook("Post Call Webhook", "cdl/post-call", 0, 600),
        respond("Acknowledge Post Call", "={{ {received:true} }}", 240, 600),
        code("Normalize Post Call", """
const message = $json.body?.message ?? {};
const phone = normalizePhone(message.customer?.number ?? message.call?.customer?.number ?? message.artifact?.variables?.customer?.number ?? '');
const callId = message.call?.id ?? $json.headers?.['x-call-id'] ?? '';
const transcript = clean(message.artifact?.transcript).slice(0, 28000);
const summary = clean(message.analysis?.summary ?? message.summary).slice(0, 2000);
const structuredData = message.analysis?.structuredData ?? {};
const readiness = clean(structuredData.readiness).replace(/_/g, ' ');
const experience = clean(structuredData.experience);
const city = clean(structuredData.city);
const state = clean(structuredData.state).toUpperCase();
const zipCode = clean(structuredData.zipCode ?? structuredData.zip ?? structuredData.postalCode);
const temperature = readiness ? classifyTemperature(readiness) : '';
const costBreakdown = message.costBreakdown ?? {};
const toolResultMessage = (message.artifact?.messages ?? []).find(item =>
  item.role === 'tool_call_result' && item.name === 'logApplicantInfo'
);
let candidateId = '';
try {
  const toolResult = typeof toolResultMessage?.result === 'string'
    ? JSON.parse(toolResultMessage.result)
    : toolResultMessage?.result;
  candidateId = clean(toolResult?.candidateId);
} catch {}
return [{ json: {
  phone, callId, candidateId, valid: Boolean(callId && (phone || candidateId)), transcript, summary,
  endedReason: clean(message.endedReason), durationSeconds: Number(message.durationSeconds ?? 0),
  cost: Number(message.cost ?? costBreakdown.total ?? 0), costBreakdown,
  readiness, temperature, experience, city, state, zipCode,
} }];
""", 500, 600),
        zoho_request("Find Candidate for Post Call", {
            "method": "GET",
            "url": "={{ $json.candidateId ? 'https://recruit.zoho.com/recruit/v2/Candidates/' + $json.candidateId : 'https://recruit.zoho.com/recruit/v2/Candidates/search?phone=' + encodeURIComponent($json.phone || '+10000000000') + '&per_page=1' }}",
            "sendQuery": False,
        }, 760, 600),
        code("Build Post Call Note", """
const call = $('Normalize Post Call').first().json;
const candidate = Array.isArray($json.data) ? $json.data[0] : null;
const money = value => Number(value ?? 0).toFixed(4);
const zipValid = /^\d{5}(?:-\d{4})?$/.test(call.zipCode || '');
const location = [call.city, call.state].filter(Boolean).join(', ') || 'not provided';
const content = [
  `VAPI Call ID: ${call.callId}`,
  `Ended reason: ${call.endedReason || 'unknown'}`,
  `Duration seconds: ${call.durationSeconds}`,
  `Total cost: $${money(call.cost)}`,
  `Cost breakdown: STT $${money(call.costBreakdown?.stt)}, LLM $${money(call.costBreakdown?.llm)}, TTS $${money(call.costBreakdown?.tts)}, VAPI $${money(call.costBreakdown?.vapi)}`,
  [
    'Candidate snapshot:',
    `Readiness: ${call.readiness || 'not provided'}`,
    `Lead temperature: ${call.temperature || 'unknown'}`,
    `Experience: ${call.experience || 'not provided'}`,
  ].join('\\n'),
  [
    'Postcode analysis:',
    `ZIP code: ${call.zipCode || 'not provided'}`,
    `ZIP prefix: ${call.zipCode ? call.zipCode.slice(0, 3) : 'not available'}`,
    `City / state: ${location}`,
    `Valid US ZIP: ${zipValid ? 'yes' : 'no'}`,
  ].join('\\n'),
  call.summary ? `Summary:\n${call.summary}` : '',
  call.transcript ? `Transcript:\n${call.transcript}` : '',
].filter(Boolean).join('\\n\\n').slice(0, 31900);
return [{ json: {
  hasCandidate: Boolean(call.valid && candidate?.id),
  noteBody: { data: [{ Note_Title: `AI Call Summary & Full Transcript — ${call.callId}`, Note_Content: content, Parent_Id: candidate?.id ?? '', se_module: 'Candidates' }] },
} }];
""", 1020, 600, helpers=False),
        condition("Post Call Candidate Found?", "={{ $json.hasCandidate }}", 1280, 600),
        zoho_request("Add Post Call Note", {
            "method": "POST",
            "url": "https://recruit.zoho.com/recruit/v2/Notes",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify($json.noteBody) }}",
        }, 1540, 560),
    ]
    connect(connections, "Post Call Webhook", "Acknowledge Post Call")
    connect(connections, "Acknowledge Post Call", "Normalize Post Call")
    connect(connections, "Normalize Post Call", "Find Candidate for Post Call")
    connect(connections, "Find Candidate for Post Call", "Build Post Call Note")
    connect(connections, "Build Post Call Note", "Post Call Candidate Found?")
    connect(connections, "Post Call Candidate Found?", "Add Post Call Note", 0)

    return {
        "name": "CDL — Production Intake, Routing & Booking",
        "nodes": nodes,
        "connections": connections,
        "settings": {
            "executionOrder": "v1",
            "timezone": "America/Vancouver",
            "saveDataErrorExecution": "all",
            "saveDataSuccessExecution": "none",
            "saveManualExecutions": True,
            "saveExecutionProgress": True,
        },
        "active": False,
        "tags": [],
        "meta": {
            "managedBy": "scripts/build_production_workflow.py",
            "version": 1,
            "deploymentStatus": "local-only",
        },
    }


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(build(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
