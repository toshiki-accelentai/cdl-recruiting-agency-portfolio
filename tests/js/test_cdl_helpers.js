const assert = require('node:assert/strict');
const {
  normalizePhone,
  splitName,
  parseExperienceYears,
  classifyTemperature,
  parseLocation,
  validateCallback,
} = require('../../workflow-src/cdl_helpers.js');

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
