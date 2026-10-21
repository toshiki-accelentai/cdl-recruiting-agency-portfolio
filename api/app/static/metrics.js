/* Read-only metric definitions. No provider outcome is inferred from a saved callback request. */
(function (root) {
  "use strict";

  function dayKey(value, timeZone) {
    var parts = new Intl.DateTimeFormat("en-US", { timeZone: timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(value);
    var date = {};
    parts.forEach(function (part) { date[part.type] = part.value; });
    return date.year + "-" + date.month + "-" + date.day;
  }

  function period(days, now, timeZone) {
    if ([1, 7, 30].indexOf(days) === -1) throw new Error("Unsupported reporting period");
    now = now || new Date();
    timeZone = timeZone || "America/Vancouver";
    var end = dayKey(now, timeZone);
    var cursor = new Date(end + "T12:00:00Z");
    cursor.setUTCDate(cursor.getUTCDate() - days + 1);
    var keys = [];
    for (var i = 0; i < days; i++) {
      keys.push(cursor.toISOString().slice(0, 10));
      cursor.setUTCDate(cursor.getUTCDate() + 1);
    }
    return { days: days, start: keys[0], end: end, keys: keys, now: now.getTime(), timeZone: timeZone };
  }

  function rate(numerator, denominator) { return denominator ? numerator / denominator * 100 : null; }

  function summarize(calls, range) {
    var result = {
      total: 0, success: 0, flaggedIntake: 0, unlinked: 0, successRate: null,
      callbackRequests: 0, callbackRate: null, people: 0,
      sync: { sent: 0, pending: 0, failed: 0, untracked: 0 }, syncRate: null,
      readiness: { HOT: 0, MEDIUM: 0, WARM: 0, COLD: 0, unknown: 0 },
      followUp: { to_call: 0, called: 0, no_answer: 0, done: 0, unknown: 0 },
      series: range.keys.map(function (key) { return { date: key, count: 0 }; })
    };
    var seen = Object.create(null), latest = Object.create(null), days = Object.create(null);
    result.series.forEach(function (day) { days[day.date] = day; });
    calls.forEach(function (call) {
      var timestamp = new Date(call.created_at).getTime();
      if (!Number.isFinite(timestamp) || timestamp > range.now || call.id == null || seen[call.id]) return;
      var key = dayKey(new Date(timestamp), range.timeZone);
      if (!days[key]) return;
      seen[call.id] = true;
      result.total++;
      days[key].count++;
      var person = call.applicant;
      if (!person || person.id == null) result.unlinked++;
      else {
        if (call.needs_review === false) result.success++;
        else result.flaggedIntake++;
        if (!latest[person.id] || timestamp > latest[person.id].timestamp ||
            (timestamp === latest[person.id].timestamp && Number(call.id) > latest[person.id].callId)) {
          latest[person.id] = { person: person, timestamp: timestamp, callId: Number(call.id) };
        }
      }
      if (call.preferred_callback_at && Number.isFinite(new Date(call.preferred_callback_at).getTime())) result.callbackRequests++;
      var sync = call.sync && call.sync.status;
      if (["sent", "pending", "failed"].indexOf(sync) !== -1) result.sync[sync]++;
      else result.sync.untracked++;
    });
    Object.keys(latest).forEach(function (id) {
      var person = latest[id].person;
      result.people++;
      var heat = person.temperature;
      result.readiness[Object.prototype.hasOwnProperty.call(result.readiness, heat) ? heat : "unknown"]++;
      var status = person.follow_up && person.follow_up.status;
      result.followUp[Object.prototype.hasOwnProperty.call(result.followUp, status) ? status : "unknown"]++;
    });
    result.successRate = rate(result.success, result.total);
    result.callbackRate = rate(result.callbackRequests, result.total);
    result.syncRate = rate(result.sync.sent, result.sync.sent + result.sync.pending + result.sync.failed);
    return result;
  }

  var api = { dayKey: dayKey, period: period, summarize: summarize };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.DeskMetrics = api;
})(typeof window !== "undefined" ? window : this);
