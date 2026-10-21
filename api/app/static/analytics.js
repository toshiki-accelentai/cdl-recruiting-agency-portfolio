(function () {
  "use strict";

  var Desk = window.Desk, Metrics = window.DeskMetrics;
  var $ = Desk.$, el = Desk.el;
  var PAGE_SIZE = 200, PAGES_PER_BATCH = 5;
  var state = { days: 7, calls: [], offset: 0, total: 0, range: null, loading: false, complete: false, request: 0, controller: null };
  var numbers = new Intl.NumberFormat("en-US");

  function count(value) { return numbers.format(value); }
  function percent(value) { return value == null ? "N/A" : new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 }).format(value) + "%"; }
  function dateLabel(key) { return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" }).format(new Date(key + "T12:00:00Z")); }

  function notice(text, label, action, isError) {
    var slot = $("analytics-notice");
    slot.replaceChildren();
    if (!text) return;
    var box = el("div", { cls: "analytics-notice" + (isError ? " is-error" : ""), attrs: { role: isError ? "alert" : "status" } }, el("span", { text: text }));
    if (label) {
      var button = el("button", { cls: "btn", text: label, attrs: { type: "button" } });
      button.addEventListener("click", action);
      box.appendChild(button);
    }
    slot.appendChild(box);
  }

  function breakdownRow(label, value, total, badge, cls) {
    var heading = el("div", { cls: "breakdown-heading" }, badge || el("span", { text: label }),
      el("span", { cls: "breakdown-value", text: count(value) }, el("small", { text: total ? percent(value / total * 100) : "N/A" })));
    var fill = el("span", { cls: "breakdown-fill" + (cls ? " " + cls : "") });
    fill.style.width = (total ? value / total * 100 : 0) + "%";
    return el("li", { cls: "breakdown-row" }, heading, el("div", { cls: "breakdown-track", attrs: { "aria-hidden": "true" } }, fill));
  }

  function renderVolume(data) {
    var plot = $("volume-plot"), table = $("volume-table");
    plot.replaceChildren(); table.replaceChildren();
    plot.classList.toggle("is-dense", data.series.length > 7);
    plot.setAttribute("aria-label", count(data.total) + " recorded calls across " + state.days + (state.days === 1 ? " day" : " days") + ". Daily counts are available below.");
    var peak = Math.max.apply(null, data.series.map(function (day) { return day.count; }).concat([1]));
    var ceiling = peak <= 4 ? 4 : Math.ceil(peak / 10) * 10;
    var axis = el("div", { cls: "volume-axis", attrs: { "aria-hidden": "true" } }, el("span", { text: count(ceiling) }), el("span", { text: count(ceiling / 2) }), el("span", { text: "0" }));
    var bars = el("div", { cls: "volume-bars", attrs: { "aria-hidden": "true" } });
    data.series.forEach(function (day, index) {
      var label = dateLabel(day.date);
      var fill = el("span", { cls: "volume-fill" });
      fill.style.height = day.count / ceiling * 100 + "%";
      var stem = el("div", { cls: "volume-stem", attrs: { title: label + ": " + count(day.count) + (day.count === 1 ? " call" : " calls") } }, fill);
      if (day.count) fill.appendChild(el("span", { cls: "volume-count", text: count(day.count) }));
      var visibleLabel = data.series.length <= 7 || index % 5 === 0 || index === data.series.length - 1 ? label : "";
      bars.appendChild(el("div", { cls: "volume-day" }, stem, el("span", { cls: "volume-day-label", text: visibleLabel })));
      table.appendChild(el("tr", {}, el("th", { text: label, attrs: { scope: "row" } }), el("td", { text: count(day.count) })));
    });
    plot.appendChild(axis); plot.appendChild(bars);
    $("volume-total").textContent = count(data.total) + (data.total === 1 ? " call" : " calls");
    $("volume-caption").textContent = dateLabel(state.range.start) + (state.range.start === state.range.end ? "" : " – " + dateLabel(state.range.end)) + " · America/Vancouver";
  }

  function render() {
    var data = Metrics.summarize(state.calls, state.range);
    $("metric-calls").textContent = count(data.total);
    $("metric-people").textContent = count(data.people) + (data.people === 1 ? " unique applicant" : " unique applicants");
    $("metric-success").textContent = percent(data.successRate);
    $("metric-success-detail").textContent = data.total ? count(data.success) + " of " + count(data.total) + " calls · no review flag" : "No calls to evaluate";
    $("metric-callbacks").textContent = count(data.callbackRequests);
    $("metric-callbacks-detail").textContent = data.total ? percent(data.callbackRate) + " of calls · requested, not confirmed" : "No saved callback requests";
    $("metric-sync").textContent = percent(data.syncRate);
    var tracked = data.total - data.sync.untracked;
    $("metric-sync-detail").textContent = tracked ? count(data.sync.sent) + " of " + count(tracked) + " tracked calls sent" : "No tracked sync records";
    $("analytics-empty").hidden = data.total !== 0;
    renderVolume(data);
    $("intake-breakdown").replaceChildren(
      breakdownRow("Successful intake", data.success, data.total, null, "fill-accent"),
      breakdownRow("Saved, needs review", data.flaggedIntake, data.total, null, "fill-amber"),
      breakdownRow("No linked applicant", data.unlinked, data.total));
    var readiness = $("readiness-breakdown"), followUp = $("followup-breakdown");
    readiness.replaceChildren(); followUp.replaceChildren();
    ["HOT", "MEDIUM", "WARM", "COLD"].forEach(function (heat) {
      readiness.appendChild(breakdownRow(heat, data.readiness[heat], data.people, Desk.heatChip(heat)));
    });
    if (data.readiness.unknown) readiness.appendChild(breakdownRow("Not set", data.readiness.unknown, data.people, Desk.heatChip(null)));
    ["to_call", "called", "no_answer", "done"].forEach(function (status) {
      followUp.appendChild(breakdownRow(status, data.followUp[status], data.people, Desk.followUpChip(status)));
    });
    if (data.followUp.unknown) followUp.appendChild(breakdownRow("Not set", data.followUp.unknown, data.people, Desk.followUpChip(null)));
    document.querySelectorAll(".applicant-cohort").forEach(function (node) { node.textContent = "Current status · " + count(data.people) + (data.people === 1 ? " unique applicant" : " unique applicants") + " in this period"; });
    $("analytics-coverage").textContent = "All recorded calls in this period · Updated " + Desk.timeText(new Date(state.range.now)) + " · America/Vancouver";
    var syncNote = count(data.sync.pending) + " pending · " + count(data.sync.failed) + " failed" + (data.sync.untracked ? " · " + count(data.sync.untracked) + " without a sync record" : "");
    $("metric-sync-detail").appendChild(el("span", { cls: "metric-secondary", text: syncNote }));
    $("analytics-content").hidden = false;
  }

  async function load(reset) {
    if (state.controller) state.controller.abort();
    var id = ++state.request;
    if (reset || !state.range) {
      state.calls = []; state.offset = 0; state.total = 0; state.complete = false;
      state.range = Metrics.period(state.days, new Date(), Desk.TZ);
    }
    state.loading = true;
    state.controller = new AbortController();
    $("analytics-content").hidden = true;
    $("analytics-refresh").disabled = true;
    $("analytics-coverage").textContent = "Loading recorded calls for " + dateLabel(state.range.start) + (state.range.start === state.range.end ? "" : " – " + dateLabel(state.range.end)) + "…";
    notice("Calculating metrics from your saved call records…");
    try {
      for (var pageIndex = 0; pageIndex < PAGES_PER_BATCH && !state.complete; pageIndex++) {
        var response = await fetch("/api/calls?sort=newest&limit=" + PAGE_SIZE + "&offset=" + state.offset, { headers: { Accept: "application/json" }, signal: state.controller.signal });
        if (response.status === 401) { Desk.toLogin(); return; }
        if (!response.ok) throw new Error("Could not load call records");
        var page = await response.json();
        if (id !== state.request) return;
        if (!Array.isArray(page.items) || !Number.isInteger(page.total) || page.total < 0 ||
            page.items.some(function (call) { return call.id == null || typeof call.created_at !== "string" || !Number.isFinite(new Date(call.created_at).getTime()); })) throw new Error("Invalid call records");
        if (!page.items.length && state.offset < page.total) throw new Error("Incomplete call records");
        state.calls = state.calls.concat(page.items);
        state.offset += page.items.length;
        state.total = page.total;
        // The existing endpoint sorts newest first; older records cannot enter this date window.
        var reachedStart = page.items.some(function (call) { return Metrics.dayKey(new Date(call.created_at), Desk.TZ) < state.range.start; });
        state.complete = reachedStart || state.offset >= state.total;
        $("analytics-coverage").textContent = "Loaded " + count(state.offset) + " recorded calls…";
      }
      if (state.complete) { notice(""); render(); }
      else {
        $("analytics-coverage").textContent = "This period needs more call records before metrics can be calculated.";
        notice("Loaded " + count(state.offset) + " of " + count(state.total) + " records. No partial rates are shown.", "Load more calls", function () { load(false); });
      }
    } catch (error) {
      if (id !== state.request || error.name === "AbortError") return;
      $("analytics-coverage").textContent = "Metrics are unavailable until the full period can be loaded.";
      notice("Couldn’t load analytics. Check your connection and try again.", "Retry", function () { load(true); }, true);
    } finally {
      if (id === state.request) { state.loading = false; $("analytics-refresh").disabled = false; }
    }
  }

  $("analytics-period").addEventListener("click", function (event) {
    var button = event.target.closest("button[data-days]");
    if (!button || Number(button.getAttribute("data-days")) === state.days) return;
    state.days = Number(button.getAttribute("data-days"));
    $("analytics-period").querySelectorAll("button").forEach(function (item) { item.setAttribute("aria-pressed", String(item === button)); });
    load(true);
  });
  $("analytics-refresh").addEventListener("click", function () { load(true); });
  window.addEventListener("desk:route", function (event) {
    if (event.detail.route === "analytics" && !state.loading) load(true);
    else if (event.detail.route !== "analytics" && state.loading) {
      state.controller.abort(); state.request++; state.loading = false;
      $("analytics-refresh").disabled = false;
    }
  });
  if (Desk.currentRoute === "analytics") load(true);
})();
