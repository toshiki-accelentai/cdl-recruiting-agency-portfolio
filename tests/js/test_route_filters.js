/* Offline checks for reading filters out of the page address (#applicants?status=to_call). No browser, no API. */
const assert = require("node:assert/strict");
const path = require("node:path");
const filters = require(path.resolve(__dirname, "../../api/app/static/route_filters.js"));

// the four links the Overview tiles use
assert.deepEqual(filters.parse("#activity?day=today"), { route: "activity", params: { day: "today" } });
assert.deepEqual(filters.parse("#applicants?status=needs_contact"), { route: "applicants", params: { status: "needs_contact" } });
assert.deepEqual(filters.parse("#applicants?status=needs_contact&readiness=hot"),
  { route: "applicants", params: { status: "needs_contact", readiness: "hot" } });
assert.deepEqual(filters.parse("#applicants?status=to_call"), { route: "applicants", params: { status: "to_call" } });
assert.deepEqual(filters.parse("#activity?sync=failed"), { route: "activity", params: { sync: "failed" } });

// plain routes and the leading slash form carry no filters
assert.deepEqual(filters.parse("#overview"), { route: "overview", params: {} });
assert.deepEqual(filters.parse("#/applicants"), { route: "applicants", params: {} });
assert.deepEqual(filters.parse(""), { route: "overview", params: {} });
assert.deepEqual(filters.parse("#nonsense?status=done"), { route: "overview", params: {} });

// only known filters with known values get through
assert.deepEqual(filters.parse("#applicants?status=bogus&readiness=hot"), { route: "applicants", params: { readiness: "hot" } });
assert.deepEqual(filters.parse("#activity?sync=failed&evil=1&day=yesterday"), { route: "activity", params: { sync: "failed" } });
assert.deepEqual(filters.parse("#applicants?sync=failed"), { route: "applicants", params: {} }, "a filter of another page is ignored");
assert.deepEqual(filters.parse("#analytics?status=done"), { route: "analytics", params: {} });

// odd input never throws and never lets markup or script through
assert.deepEqual(filters.parse("#applicants?status=<script>"), { route: "applicants", params: {} });
assert.deepEqual(filters.parse("#applicants?status=%E0%A4%A"), { route: "applicants", params: {} });
assert.deepEqual(filters.parse("#applicants?status=done&status=called"), { route: "applicants", params: { status: "done" } });
assert.deepEqual(filters.parse("#applicants?&&=&status=done"), { route: "applicants", params: { status: "done" } });
assert.deepEqual(filters.parse(null), { route: "overview", params: {} });

// the other filters of Call activity
assert.deepEqual(filters.parse("#activity?review=true&follow_up=no_answer"),
  { route: "activity", params: { review: "true", follow_up: "no_answer" } });

console.log("route filters: tile links, plain routes, unknown or unsafe input all handled");
