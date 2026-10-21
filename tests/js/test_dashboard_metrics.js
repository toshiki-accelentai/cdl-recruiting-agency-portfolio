/* Offline checks for the call-data metrics shown to recruiters. No API or database access. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const root = path.resolve(__dirname, "../..");
const metrics = require(path.join(root, "api/app/static/metrics.js"));

const now = new Date("2026-10-20T19:00:00Z");
const period = metrics.period(7, now, "America/Vancouver");
function call(id, overrides = {}) {
  return Object.assign({ id, created_at: "2026-10-20T15:00:00Z", needs_review: false,
    applicant: { id, temperature: "HOT", follow_up: { status: "to_call" } },
    preferred_callback_at: null, sync: { status: "sent" } }, overrides);
}

assert.equal(period.start, "2026-10-14");
assert.equal(period.end, "2026-10-20");
assert.equal(period.keys.length, 7);
assert.equal(metrics.period(1, new Date("2026-10-20T06:30:00Z"), "America/Vancouver").start, "2026-10-19");
assert.equal(metrics.period(30, new Date("2026-11-03T20:00:00Z"), "America/Vancouver").keys.length, 30);

const rows = [
  call(1, { preferred_callback_at: "2026-10-21T16:00:00Z" }),
  call(2, { needs_review: true, sync: { status: "failed" } }),
  call(3, { applicant: null, needs_review: true, sync: null }),
  call(4, { applicant: { id: 1, temperature: "COLD", follow_up: { status: "done" } },
    created_at: "2026-10-20T18:00:00Z", sync: { status: "pending" } }),
  call(5, { created_at: "2026-10-14T06:59:59Z" }), // Previous business date.
  call(6, { created_at: "2026-10-14T07:00:00Z" }), // First second of the period.
  call(7, { created_at: "2026-10-20T21:00:00Z" }), // Future timestamps are not received calls.
  call(8, { created_at: "invalid date" })
];
const data = metrics.summarize(rows.concat(rows[0]), period);
assert.equal(data.total, 5, "calls count once, within the business date window");
assert.equal(data.success, 3, "success requires an applicant and no review flag");
assert.equal(data.successRate, 60);
assert.equal(data.flaggedIntake, 1);
assert.equal(data.unlinked, 1);
assert.equal(data.success + data.flaggedIntake + data.unlinked, data.total);
assert.equal(data.callbackRequests, 1, "requests are not described as confirmed bookings");
assert.equal(data.callbackRate, 20);
assert.equal(data.sync.sent, 2);
assert.equal(data.sync.pending, 1);
assert.equal(data.sync.failed, 1);
assert.equal(data.sync.untracked, 1);
assert.equal(data.syncRate, 50, "sync rate excludes calls with no sync record");
assert.equal(data.people, 3, "repeat calls do not inflate unique applicants");
assert.equal(data.readiness.COLD, 1, "use each person's most recent profile in this period");
assert.equal(data.readiness.HOT, 2);
assert.equal(data.followUp.done, 1);
assert.equal(data.series.reduce((sum, day) => sum + day.count, 0), data.total);
assert.deepEqual(metrics.summarize(rows.slice().reverse(), period), metrics.summarize(rows, period),
  "metrics do not depend on input order");

const empty = metrics.summarize([], period);
assert.equal(empty.total, 0);
assert.equal(empty.successRate, null, "no calls is not a zero percent failure rate");
assert.equal(empty.callbackRate, null);
assert.equal(empty.syncRate, null);
assert.equal(empty.series.length, 7);
const unknown = metrics.summarize([call(9, { applicant: { id: 9, temperature: "UNSET", follow_up: { status: "other" } }, sync: { status: "other" } })], period);
assert.equal(unknown.readiness.unknown, 1);
assert.equal(unknown.followUp.unknown, 1);
assert.equal(unknown.syncRate, null);

// Status can be read from words and readiness bars as well as hue.
const context = { window: {}, document: { createElement(tag) {
  return { tag, children: [], attrs: {}, setAttribute(k, v) { this.attrs[k] = v; }, appendChild(child) { this.children.push(child); } };
} } };
vm.runInNewContext(fs.readFileSync(path.join(root, "api/app/static/common.js"), "utf8"), context);
const desk = context.window.Desk;
const chips = ["HOT", "MEDIUM", "WARM", "COLD"].map(value => desk.heatChip(value));
assert.equal(new Set(chips.map(chip => chip.className)).size, 4);
assert.deepEqual(chips.map(chip => chip.children[1].textContent), ["Hot", "Medium", "Warm", "Cold"]);
assert.equal(desk.heatChip(null).children[1].textContent, "Not set");
const statuses = ["to_call", "called", "no_answer", "done"].map(value => desk.followUpChip(value));
assert.equal(new Set(statuses.map(chip => chip.className)).size, 4);
assert.deepEqual(statuses.map(chip => chip.children[1].textContent), ["To contact", "Called", "No answer", "Done"]);
assert.equal(desk.followUpChip("other").children[1].textContent, "Not set");

console.log("dashboard metrics: date boundaries, denominators, duplicate calls, applicant cohorts, empty/unknown data and status cues passed");
