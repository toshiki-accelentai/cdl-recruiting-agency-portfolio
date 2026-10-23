const assert = require('node:assert/strict');
const {
  BUSINESS_TIMEZONE,
  normalizePhone,
  pickPhone,
  splitName,
  parseExperienceYears,
  classifyTemperature,
  parseLocation,
  validateLocation,
  validateCallback,
} = require('../../workflow-src/cdl_helpers.js');

assert.equal(BUSINESS_TIMEZONE, 'America/Vancouver');

assert.equal(normalizePhone('(206) 555-1234'), '+12065551234');
assert.equal(normalizePhone('+1 206 555 1234'), '+12065551234');
assert.equal(normalizePhone('206-555-123'), null);

assert.deepEqual(splitName('Jane Doe'), { firstName: 'Jane', lastName: 'Doe' });
assert.deepEqual(splitName('Madonna'), { firstName: '', lastName: 'Madonna' });
assert.deepEqual(splitName('  Mary Jane Watson  '), {
  firstName: 'Mary Jane',
  lastName: 'Watson',
});

assert.equal(parseExperienceYears('No experience / just got CDL'), 0);
assert.equal(parseExperienceYears('Under 6 months'), 0.25);
assert.equal(parseExperienceYears('6-12 months'), 0.75);
assert.equal(parseExperienceYears('1-2 years'), 1.5);
assert.equal(parseExperienceYears('2+ years'), 2);
assert.equal(parseExperienceYears('5+ years'), 5);
assert.equal(parseExperienceYears('18 months'), 1.5);

assert.equal(classifyTemperature('within 3 days'), 'HOT');
assert.equal(classifyTemperature('within 7 days'), 'MEDIUM');
assert.equal(classifyTemperature('within 14 days'), 'WARM');
assert.equal(classifyTemperature('later'), 'COLD');

assert.deepEqual(parseLocation({ city: 'Seattle', state: 'WA', zipCode: '98101' }), {
  city: 'Seattle', state: 'WA', zipCode: '98101',
});
assert.deepEqual(parseLocation({ driverLocation: 'Seattle, WA 98101' }), {
  city: 'Seattle', state: 'WA', zipCode: '98101',
});

// Phone: an empty or garbled spoken number falls back to the caller ID.
assert.equal(pickPhone('', '+12065551234'), '+12065551234');
assert.equal(pickPhone('206-555-12', '+12065551234'), '+12065551234');
assert.equal(pickPhone('(425) 555-9876', '+12065551234'), '+14255559876');
assert.equal(pickPhone(undefined, undefined), null);

// Names: surname particles and suffixes stay with the last name.
assert.deepEqual(splitName('Maria De La Cruz'), { firstName: 'Maria', lastName: 'De La Cruz' });
assert.deepEqual(splitName('John Smith Jr.'), { firstName: 'John', lastName: 'Smith Jr.' });
assert.deepEqual(splitName('Smith Jr.'), { firstName: '', lastName: 'Smith Jr.' });

// Experience: years and months add up; unreadable text is null, not 0.
assert.equal(parseExperienceYears('2 years 6 months'), 2.5);
assert.equal(parseExperienceYears('5 yrs'), 5);
assert.equal(parseExperienceYears('five years'), 5);
assert.equal(parseExperienceYears('3 to 5 years'), 4);
assert.equal(parseExperienceYears('a year'), 1);
assert.equal(parseExperienceYears('10+ years'), 10);
assert.equal(parseExperienceYears(''), null);
assert.equal(parseExperienceYears('a long time'), null);

// Temperature: the voice agent picks one of four fixed answers; the code only maps them.
for (const [text, expected] of [
  ['within 3 days', 'HOT'], ['Within 7 Days', 'MEDIUM'], ['within_14_days', 'WARM'],
  [' later ', 'COLD'],
]) {
  assert.equal(classifyTemperature(text), expected, `temperature of "${text}"`);
}
// Anything else is unknown, never silently COLD.
for (const text of ['tomorrow', '13 days', 'this week', '', undefined, null]) {
  assert.equal(classifyTemperature(text), 'UNKNOWN', `temperature of "${text}"`);
}

// Location: state must be a real US code, ZIP exactly 5 digits.
assert.equal(parseLocation({ city: 'Dallas', state: 'Texas', zipCode: '75201' }).state, 'TX');
assert.equal(parseLocation({ city: 'Dallas', state: 'tx', zipCode: '75201-1234' }).zipCode, '75201');
assert.deepEqual(validateLocation({ city: 'Dallas', state: 'TX', zipCode: '75201' }), []);
assert.deepEqual(validateLocation({ city: '', state: '', zipCode: '' }),
  ['missing_city', 'missing_state', 'missing_zip_code']);
assert.deepEqual(validateLocation({ city: 'Dallas', state: 'ZZ', zipCode: '7520' }),
  ['invalid_state', 'invalid_zip_code']);

const valid = validateCallback('2026-08-13T10:00:00', new Date('2026-08-12T12:00:00Z'));
assert.equal(valid.valid, true);
assert.equal(valid.startUtc, '2026-08-13T17:00:00.000Z');
assert.equal(valid.endUtc, '2026-08-13T17:15:00.000Z');

assert.equal(
  validateCallback('2026-08-15T10:00:00', new Date('2026-08-12T12:00:00Z')).reason,
  'weekend',
);
assert.equal(
  validateCallback('2026-08-13T08:59:00', new Date('2026-08-12T12:00:00Z')).reason,
  'before_open',
);
assert.equal(
  validateCallback('2026-08-13T17:00:00', new Date('2026-08-12T12:00:00Z')).reason,
  'after_close',
);

console.log('cdl_helpers: all assertions passed');
