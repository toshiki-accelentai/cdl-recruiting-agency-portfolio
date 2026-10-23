'use strict';

const BUSINESS_TIMEZONE = 'America/Vancouver';
const BUSINESS_START_HOUR = 9;
const BUSINESS_END_HOUR = 17;
const CALLBACK_MINUTES = 15;

function clean(value) {
  return typeof value === 'string' ? value.trim() : '';
}

function normalizePhone(value) {
  let digits = clean(value).replace(/\D/g, '');
  if (digits.length === 10) digits = `1${digits}`;
  if (digits.length !== 11 || !digits.startsWith('1')) return null;
  return `+${digits}`;
}

// A spoken number that is empty or garbled must not hide a usable caller ID.
function pickPhone(...candidates) {
  for (const candidate of candidates) {
    const phone = normalizePhone(candidate);
    if (phone) return phone;
  }
  return null;
}

const NAME_SUFFIXES = new Set(['jr', 'jr.', 'sr', 'sr.', 'ii', 'iii', 'iv']);
const SURNAME_PARTICLES = new Set(['de', 'del', 'della', 'la', 'le', 'da', 'di', 'du', 'van', 'von', 'der', 'den', 'st', 'st.']);

function splitName(value) {
  const parts = clean(value).split(/\s+/).filter(Boolean);
  if (parts.length === 0) return { firstName: '', lastName: 'Unknown' };

  // The last name runs from its first particle ("De La") to the end, suffix ("Jr.") included.
  let end = parts.length;
  while (end > 1 && NAME_SUFFIXES.has(parts[end - 1].toLowerCase())) end -= 1;
  let start = end - 1;
  while (start > 1 && SURNAME_PARTICLES.has(parts[start - 1].toLowerCase())) start -= 1;
  return { firstName: parts.slice(0, start).join(' '), lastName: parts.slice(start).join(' ') };
}

const NUMBER_WORDS = {
  a: 1, an: 1, one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8,
  nine: 9, ten: 10, eleven: 11, twelve: 12, thirteen: 13, fourteen: 14, fifteen: 15,
  sixteen: 16, seventeen: 17, eighteen: 18, nineteen: 19, twenty: 20,
};

// Turns "five years", "a year", "3 to 5 years" into digits so one set of patterns can read them.
function digitizeNumbers(text) {
  return text
    .replace(new RegExp(`\\b(${Object.keys(NUMBER_WORDS).join('|')})\\b(?=[\\s-]*(?:years?|yrs?|months?|days?|weeks?)\\b)`, 'g'),
      (word) => String(NUMBER_WORDS[word]))
    .replace(/(\d)\s*to\s*(\d)/g, '$1-$2');
}

function rangeOrSingle(text, unit) {
  const range = text.match(new RegExp(`(\\d+(?:\\.\\d+)?)\\s*-\\s*(\\d+(?:\\.\\d+)?)\\s*${unit}`));
  if (range) return (Number(range[1]) + Number(range[2])) / 2;
  const single = text.match(new RegExp(`(\\d+(?:\\.\\d+)?)\\s*\\+?\\s*${unit}`));
  return single ? Number(single[1]) : null;
}

// Years of CDL experience, or null when the text cannot be read (null is not the same as 0).
function parseExperienceYears(value) {
  const text = digitizeNumbers(clean(value).toLowerCase().replace(/[–—]/g, '-'));
  if (/no experience|just got|new cdl/.test(text)) return 0;
  if (/(?:under|less than)\s*6\s*months?/.test(text)) return 0.25;

  const years = rangeOrSingle(text, '(?:years?|yrs?)\\b');
  const months = rangeOrSingle(text, 'months?\\b');
  if (years === null && months === null) return null;
  return Number(((years ?? 0) + (months ?? 0) / 12).toFixed(2));
}

// The VAPI tool restricts `readiness` to these four answers (see tool.logApplicantInfo.desired.json);
// the voice agent does the judging of "tomorrow", "this week", etc., the code only maps the answer.
const TEMPERATURE_BY_READINESS = {
  'within 3 days': 'HOT',
  'within 7 days': 'MEDIUM',
  'within 14 days': 'WARM',
  'later': 'COLD',
};

// UNKNOWN means "not one of the four answers", so a recruiter can look; it is not the same as COLD.
function classifyTemperature(value) {
  const key = clean(value).toLowerCase().replace(/_/g, ' ');
  return TEMPERATURE_BY_READINESS[key] ?? 'UNKNOWN';
}

const US_STATES = {
  AL: 'alabama', AK: 'alaska', AZ: 'arizona', AR: 'arkansas', CA: 'california', CO: 'colorado',
  CT: 'connecticut', DE: 'delaware', DC: 'district of columbia', FL: 'florida', GA: 'georgia',
  HI: 'hawaii', ID: 'idaho', IL: 'illinois', IN: 'indiana', IA: 'iowa', KS: 'kansas',
  KY: 'kentucky', LA: 'louisiana', ME: 'maine', MD: 'maryland', MA: 'massachusetts',
  MI: 'michigan', MN: 'minnesota', MS: 'mississippi', MO: 'missouri', MT: 'montana',
  NE: 'nebraska', NV: 'nevada', NH: 'new hampshire', NJ: 'new jersey', NM: 'new mexico',
  NY: 'new york', NC: 'north carolina', ND: 'north dakota', OH: 'ohio', OK: 'oklahoma',
  OR: 'oregon', PA: 'pennsylvania', RI: 'rhode island', SC: 'south carolina', SD: 'south dakota',
  TN: 'tennessee', TX: 'texas', UT: 'utah', VT: 'vermont', VA: 'virginia', WA: 'washington',
  WV: 'west virginia', WI: 'wisconsin', WY: 'wyoming',
};

// "Texas" and "tx" both become "TX". Anything unknown stays as typed so validateLocation can reject it.
function normalizeState(value) {
  const text = clean(value);
  const code = text.toUpperCase();
  if (code in US_STATES) return code;
  const byName = Object.entries(US_STATES).find(([, name]) => name === text.toLowerCase());
  return byName ? byName[0] : code;
}

// "98101" and "98101-1234" both become "98101". Anything else stays as typed so validateLocation can reject it.
function normalizeZip(value) {
  const text = clean(value).replace(/\s+/g, '');
  const match = text.match(/^(\d{5})(?:-\d{4})?$/);
  return match ? match[1] : text;
}

function validateLocation({ city, state, zipCode }) {
  const errors = [];
  if (!city) errors.push('missing_city');
  if (!state) errors.push('missing_state');
  else if (!(state in US_STATES)) errors.push('invalid_state');
  if (!zipCode) errors.push('missing_zip_code');
  else if (!/^\d{5}$/.test(zipCode)) errors.push('invalid_zip_code');
  return errors;
}

function parseLocation(args = {}) {
  let city = clean(args.city);
  let state = clean(args.state);
  let zipCode = clean(args.zipCode || args.zip || args.postalCode);
  const legacy = clean(args.driverLocation);

  if (legacy && (!city || !state || !zipCode)) {
    const match = legacy.match(/^(.+?)(?:,\s*|\s+)([A-Za-z]{2})(?:\s+(\d{5}(?:-\d{4})?))?$/);
    if (match) {
      city ||= match[1].trim();
      state ||= match[2].toUpperCase();
      zipCode ||= match[3] || '';
    } else if (!city) {
      city = legacy;
    }
  }
  return { city, state: normalizeState(state), zipCode: normalizeZip(zipCode) };
}

function zonedParts(date, timeZone = BUSINESS_TIMEZONE) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
    weekday: 'short', hourCycle: 'h23',
  }).formatToParts(date).reduce((result, part) => {
    if (part.type !== 'literal') result[part.type] = part.value;
    return result;
  }, {});
  return {
    year: Number(parts.year), month: Number(parts.month), day: Number(parts.day),
    hour: Number(parts.hour), minute: Number(parts.minute), second: Number(parts.second),
    weekday: parts.weekday,
  };
}

function offsetAt(date, timeZone = BUSINESS_TIMEZONE) {
  const p = zonedParts(date, timeZone);
  return Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second) - date.getTime();
}

function localPartsToUtc(parts, timeZone = BUSINESS_TIMEZONE) {
  const wallClock = Date.UTC(parts.year, parts.month - 1, parts.day, parts.hour, parts.minute, parts.second || 0);
  let candidate = new Date(wallClock);
  for (let attempt = 0; attempt < 3; attempt += 1) {
    candidate = new Date(wallClock - offsetAt(candidate, timeZone));
  }
  const roundTrip = zonedParts(candidate, timeZone);
  const matches = ['year', 'month', 'day', 'hour', 'minute'].every((key) => roundTrip[key] === parts[key]);
  return matches ? candidate : null;
}

function nthWeekday(year, month, weekday, occurrence) {
  const first = new Date(Date.UTC(year, month - 1, 1));
  const day = 1 + ((7 + weekday - first.getUTCDay()) % 7) + ((occurrence - 1) * 7);
  return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

function lastWeekday(year, month, weekday) {
  const last = new Date(Date.UTC(year, month, 0));
  const day = last.getUTCDate() - ((7 + last.getUTCDay() - weekday) % 7);
  return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

function observedDate(year, month, day) {
  const date = new Date(Date.UTC(year, month - 1, day));
  if (date.getUTCDay() === 6) date.setUTCDate(date.getUTCDate() - 1);
  if (date.getUTCDay() === 0) date.setUTCDate(date.getUTCDate() + 1);
  return date.toISOString().slice(0, 10);
}

function federalHolidays(year) {
  return new Set([
    observedDate(year, 1, 1),
    nthWeekday(year, 1, 1, 3),
    nthWeekday(year, 2, 1, 3),
    lastWeekday(year, 5, 1),
    observedDate(year, 6, 19),
    observedDate(year, 7, 4),
    nthWeekday(year, 9, 1, 1),
    nthWeekday(year, 10, 1, 2),
    observedDate(year, 11, 11),
    nthWeekday(year, 11, 4, 4),
    observedDate(year, 12, 25),
  ]);
}

function validateCallback(value, now = new Date(), timeZone = BUSINESS_TIMEZONE) {
  const raw = clean(value);
  if (!raw) return { valid: false, reason: 'missing_callback_time', timeZone };

  let start;
  if (/(?:Z|[+-]\d{2}:?\d{2})$/.test(raw)) {
    start = new Date(raw);
  } else {
    const match = raw.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/);
    if (!match) return { valid: false, reason: 'invalid_datetime', timeZone };
    start = localPartsToUtc({
      year: Number(match[1]), month: Number(match[2]), day: Number(match[3]),
      hour: Number(match[4]), minute: Number(match[5]), second: Number(match[6] || 0),
    }, timeZone);
  }
  if (!start || Number.isNaN(start.getTime())) return { valid: false, reason: 'invalid_datetime', timeZone };
  if (start.getTime() <= now.getTime()) return { valid: false, reason: 'past_time', timeZone };

  const p = zonedParts(start, timeZone);
  const localDate = `${p.year}-${String(p.month).padStart(2, '0')}-${String(p.day).padStart(2, '0')}`;
  if (!['Mon', 'Tue', 'Wed', 'Thu', 'Fri'].includes(p.weekday)) {
    return { valid: false, reason: 'weekend', timeZone };
  }
  if (federalHolidays(p.year).has(localDate)) return { valid: false, reason: 'holiday', timeZone };
  if (p.hour < BUSINESS_START_HOUR) return { valid: false, reason: 'before_open', timeZone };
  if (p.hour >= BUSINESS_END_HOUR) return { valid: false, reason: 'after_close', timeZone };
  if (p.hour === BUSINESS_END_HOUR - 1 && p.minute > 45) {
    return { valid: false, reason: 'ends_after_close', timeZone };
  }

  return {
    valid: true,
    reason: 'within_hours',
    timeZone,
    startUtc: start.toISOString(),
    endUtc: new Date(start.getTime() + CALLBACK_MINUTES * 60_000).toISOString(),
    localDate,
  };
}

const exported = {
  BUSINESS_TIMEZONE,
  normalizePhone,
  pickPhone,
  splitName,
  parseExperienceYears,
  classifyTemperature,
  parseLocation,
  validateLocation,
  validateCallback,
};

if (typeof module !== 'undefined') module.exports = exported;
