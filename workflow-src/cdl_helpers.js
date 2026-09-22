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

function splitName(value) {
  const parts = clean(value).split(/\s+/).filter(Boolean);
  if (parts.length === 0) return { firstName: '', lastName: 'Unknown' };
  if (parts.length === 1) return { firstName: '', lastName: parts[0] };
  return { firstName: parts.slice(0, -1).join(' '), lastName: parts.at(-1) };
}

function parseExperienceYears(value) {
  const text = clean(value).toLowerCase().replace(/[–—]/g, '-');
  if (!text || /no experience|just got|new cdl/.test(text)) return 0;
  if (/under\s*6\s*months?/.test(text)) return 0.25;

  const monthRange = text.match(/(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*months?/);
  if (monthRange) return Number(((Number(monthRange[1]) + Number(monthRange[2])) / 24).toFixed(2));
  const months = text.match(/(\d+(?:\.\d+)?)\s*months?/);
  if (months) return Number((Number(months[1]) / 12).toFixed(2));

  const yearRange = text.match(/(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*years?/);
  if (yearRange) return Number(((Number(yearRange[1]) + Number(yearRange[2])) / 2).toFixed(2));
  const years = text.match(/(\d+(?:\.\d+)?)\s*\+?\s*years?/);
  return years ? Number(years[1]) : 0;
}

function classifyTemperature(value) {
  const text = clean(value).toLowerCase();
  if (/3\s*days?|immediately|right away/.test(text)) return 'HOT';
  if (/7\s*days?|one\s*week/.test(text)) return 'MEDIUM';
  if (/14\s*days?|two\s*weeks?/.test(text)) return 'WARM';
  return 'COLD';
}

function parseLocation(args = {}) {
  let city = clean(args.city);
  let state = clean(args.state).toUpperCase();
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
  return { city, state, zipCode };
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
  splitName,
  parseExperienceYears,
  classifyTemperature,
  parseLocation,
  validateCallback,
};

if (typeof module !== 'undefined') module.exports = exported;
