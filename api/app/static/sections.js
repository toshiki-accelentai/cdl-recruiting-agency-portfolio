(function () {
  "use strict";

  var Desk = window.Desk;
  var $ = Desk.$, el = Desk.el;
  var PAGE_SIZE = 50;
  var directory = { calls: [], offset: 0, total: 0, loading: false, complete: false, status: "all", readiness: "", query: "", request: 0 };
  var activity = { offset: 0, total: 0, loading: false, reload: false, request: 0, items: [], query: "" };
  var FOLLOW_UP = { to_call: "To contact", called: "Called", no_answer: "No answer", done: "Done" };
  var REASON = {
    invalid_phone: "The phone number could not be used.",
    missing_name: "The caller did not give a name.",
    no_intake: "The call ended before details were saved."
  };

  function requestJson(url) {
    return fetch(url, { headers: { Accept: "application/json" } }).then(function (response) {
      if (response.status === 401) { Desk.toLogin(); return null; }
      if (!response.ok) throw new Error("status " + response.status);
      return response.json();
    });
  }

  function followUpStatus(person) {
    var value = person.follow_up && person.follow_up.status;
    return FOLLOW_UP[value] ? value : "unknown";
  }

  function applicantRows() {
    var latestById = Object.create(null);
    directory.calls.forEach(function (call) {
      var person = call.applicant;
      if (!person || person.id == null) return;
      var key = String(person.id);
      var entry = latestById[key];
      var time = new Date(call.created_at).getTime();
      if (!entry) entry = latestById[key] = { person: person, call: call, callbackAt: null, callbackFrom: -Infinity };
      else if (time > new Date(entry.call.created_at).getTime()) { entry.person = person; entry.call = call; }
      // The most recent callback asked for, so a later call without one (a hang-up) does not hide it.
      if (call.preferred_callback_at && time > entry.callbackFrom) { entry.callbackAt = call.preferred_callback_at; entry.callbackFrom = time; }
    });
    var rows = Object.keys(latestById).map(function (id) { return latestById[id]; });
    rows.sort(function (a, b) {
      return new Date(b.call.created_at).getTime() - new Date(a.call.created_at).getTime() || Number(b.person.id) - Number(a.person.id);
    });
    var query = directory.query.trim().toLocaleLowerCase();
    return rows.filter(function (row) {
      if (directory.status === "needs_contact") {
        // the same rule as the Overview list: still to call, or called again since the last follow-up update
        var follow = row.person.follow_up || {};
        if (!(follow.status === "to_call" || follow.new_call_since)) return false;
      } else if (directory.status !== "all" && followUpStatus(row.person) !== directory.status) return false;
      if (directory.readiness && String(row.person.temperature || "").toLowerCase() !== directory.readiness) return false;
      if (!query) return true;
      var person = row.person;
      var searchable = [person.name, person.phone, person.city, person.state, person.zip_code, person.readiness,
        row.call.summary, FOLLOW_UP[followUpStatus(person)]].filter(Boolean).join(" ").toLocaleLowerCase();
      return searchable.indexOf(query) !== -1;
    });
  }

  function initials(name) {
    var words = String(name || "?").trim().split(/\s+/).filter(Boolean);
    return words.slice(0, 2).map(function (word) { return word.charAt(0).toUpperCase(); }).join("") || "?";
  }

  function statusChip(person) {
    return Desk.followUpChip(followUpStatus(person));
  }

  function renderDirectory() {
    var rows = applicantRows();
    var body = $("applicant-rows");
    body.replaceChildren();
    if (!rows.length) {
      body.appendChild(el("tr", {}, el("td", { cls: "table-empty", text: directory.calls.length ? "No applicants match these filters." : "No applicants were found in the loaded calls." , attrs: { colspan: "6" } })));
    } else {
      rows.forEach(function (row) {
        var person = row.person;
        var latest = row.call;
        var name = person.name || "No name given";
        var place = [person.city, person.state].filter(Boolean).join(", ") || person.zip_code || "Location not given";
        var readiness = el("span", { cls: "readiness-cell" }, Desk.heatChip(person.temperature));
        if (person.readiness) readiness.appendChild(el("small", { text: person.readiness }));
        var callback = row.callbackAt
          ? el("span", { cls: "callback-cell", text: Desk.whenText(row.callbackAt) })
          : el("span", { cls: "callback-cell muted", text: "No time given" });
        var callDate = el("span", { cls: "last-call-cell", text: Desk.agoText(latest.created_at), attrs: { title: Desk.whenText(latest.created_at) } });
        var link = el("a", { cls: "btn btn-sm table-open", attrs: { href: "/applicants/" + person.id, "aria-label": "Open applicant " + name } }, el("span", { text: "Open" }), Desk.icon("arrow"));
        var nameCell = el("td", { cls: "applicant-cell" }, el("span", { cls: "person-avatar", attrs: { "aria-hidden": "true" }, text: initials(name) }), el("span", {}, el("a", { cls: "table-person-name", text: name, attrs: { href: "/applicants/" + person.id } }), el("small", { text: place }), person.phone ? el("small", { cls: "mono", text: Desk.phoneText(person.phone) }) : null));
        var status = el("td", {}, statusChip(person));
        if (latest.needs_review) status.appendChild(el("span", { cls: "table-substatus", text: "Call needs review" }));
        body.appendChild(el("tr", {}, nameCell, el("td", {}, readiness), el("td", {}, callback), status, el("td", {}, callDate), el("td", { cls: "open-cell" }, link)));
      });
    }
    var scope = directory.complete
      ? "All " + directory.total + " calls are loaded. Each applicant is grouped by their most recent call."
      : "Showing applicants from the " + directory.offset + " newest of " + directory.total + " calls. Search covers loaded calls only.";
    $("applicant-scope").textContent = directory.loading ? "Loading calls… " + scope : scope;
    $("applicant-result-count").textContent = rows.length + (rows.length === 1 ? " applicant" : " applicants") + (directory.query || directory.status !== "all" || directory.readiness ? " match" : " shown");
    $("applicants-more").hidden = directory.complete || directory.loading || directory.offset >= directory.total;
    $("applicants-more").disabled = directory.loading;
    $("applicants-refresh").disabled = directory.loading;
  }

  function loadDirectory(reset) {
    if (directory.loading) return;
    if (reset) {
      directory.calls = [];
      directory.offset = 0;
      directory.total = 0;
      directory.complete = false;
    }
    directory.loading = true;
    var id = ++directory.request;
    renderDirectory();
    var url = "/api/calls?sort=newest&limit=200&offset=" + directory.offset;
    requestJson(url).then(function (page) {
      if (!page || id !== directory.request) return;
      if (!Array.isArray(page.items) || !Number.isFinite(Number(page.total))) throw new Error("invalid page");
      directory.calls = directory.calls.concat(page.items);
      directory.total = Number(page.total);
      directory.offset += page.items.length;
      if (page.items.length === 0 && directory.offset < directory.total) throw new Error("empty page before total");
      directory.complete = directory.offset >= directory.total;
      $("error-slot").replaceChildren();
    }).catch(function () {
      if (id !== directory.request) return;
      var retry = el("button", { cls: "btn", text: "Retry", attrs: { type: "button" } });
      retry.addEventListener("click", function () { loadDirectory(directory.calls.length === 0); });
      $("error-slot").replaceChildren(el("div", { cls: "banner", attrs: { role: "alert" } }, el("span", { text: "Couldn’t load the applicant list. Your saved follow-up updates are unchanged." }), retry));
    }).then(function () {
      if (id !== directory.request) return;
      directory.loading = false;
      renderDirectory();
    });
  }

  function activityParams() {
    var params = new URLSearchParams({ sort: $("activity-sort").value, limit: String(PAGE_SIZE), offset: String(activity.offset) });
    if ($("activity-day").value) params.set("day", $("activity-day").value);
    ["review", "sync", "follow-up"].forEach(function (key) {
      var id = key === "follow-up" ? "activity-follow-up" : "activity-" + key;
      var value = $(id).value;
      if (!value) return;
      if (key === "review" && value === "hang_up") params.set("kind", "hang_up");
      else params.set(key === "review" ? "needs_review" : key === "follow-up" ? "follow_up" : key, value);
    });
    return "/api/calls?" + params.toString();
  }

  function addActivityBadge(container, cls, text) {
    if (text) container.appendChild(el("span", { cls: cls, text: text }));
  }

  function activityItem(call) {
    var person = call.applicant;
    var who = person && person.id
      ? el("a", { cls: "activity-name", text: person.name || "No name given", attrs: { href: "/applicants/" + person.id } })
      : el("span", { cls: "activity-name", text: "Unlinked caller" });
    var phone = person && person.phone || call.caller_number;
    var meta = el("div", { cls: "activity-meta" },
      el("span", { cls: "activity-date", text: Desk.whenText(call.created_at), attrs: { title: Desk.agoText(call.created_at) } }));
    if (phone) meta.appendChild(Desk.phoneLink(phone));
    if (person && person.temperature) meta.appendChild(Desk.heatChip(person.temperature));
    var badges = el("div", { cls: "activity-badges" });
    // A hang-up from an unknown caller is kept but is not a recruiter's problem: a plain chip, not "Needs review".
    var hangUp = call.review_reason === "no_intake" && !(person && person.id);
    if (hangUp) addActivityBadge(badges, "status-chip", "Hang-up");
    else if (call.needs_review) addActivityBadge(badges, "status-chip status-attention", "Needs review");
    if (call.sync && call.sync.status === "failed") addActivityBadge(badges, "status-chip status-danger", "Zoho sync failed");
    else if (call.sync && call.sync.status === "pending") addActivityBadge(badges, "status-chip status-waiting", "Waiting to sync");
    else if (call.sync && call.sync.status === "sent") addActivityBadge(badges, "status-chip", "Sent to Zoho");
    if (person) badges.appendChild(Desk.followUpChip(followUpStatus(person)));

    var item = el("li", { cls: "activity-item" });
    item.appendChild(el("div", { cls: "activity-marker", attrs: { "aria-hidden": "true" } }, el("span", {})));
    var body = el("div", { cls: "activity-body" }, el("div", { cls: "activity-title-row" }, who, badges), meta);
    if (call.preferred_callback_at) body.appendChild(el("p", { cls: "activity-callback", text: "Requested callback: " + Desk.whenText(call.preferred_callback_at) }));
    if (hangUp) body.appendChild(el("p", { cls: "activity-review-reason", text: "Ended before any details were saved. The number matches no applicant." }));
    else if (call.needs_review) body.appendChild(el("p", { cls: "activity-review-reason", text: REASON[call.review_reason] || "A recruiter should review this call." }));
    if (call.summary) body.appendChild(el("p", { cls: "activity-summary", text: call.summary }));
    if (call.sync && call.sync.status === "failed") {
      var syncText = "Saved here, not in Zoho yet. " + call.sync.attempts + (call.sync.attempts === 1 ? " try." : " tries.");
      if (call.sync.last_error) syncText += " " + Desk.clip(call.sync.last_error, 150);
      body.appendChild(el("p", { cls: "activity-sync-note", text: syncText }));
    }
    if (call.has_recording) {
      var details = el("details", { cls: "activity-details" });
      details.appendChild(el("summary", { text: "Listen to call recording" }));
      details.appendChild(el("audio", { attrs: { controls: "", preload: "none", src: "/api/calls/" + call.id + "/recording", "aria-label": "Call recording" } }));
      body.appendChild(details);
    }
    item.appendChild(body);
    return item;
  }

  function renderActivity() {
    var list = $("activity-list");
    var visible = activity.items.filter(function (call) {
      if (!activity.query) return true;
      var person = call.applicant || {};
      return [person.name, person.phone, person.city, person.state, call.caller_number, call.summary, call.id].filter(Boolean).join(" ").toLocaleLowerCase().indexOf(activity.query) >= 0;
    });
    list.replaceChildren();
    if (!visible.length) list.appendChild(el("li", { cls: "table-empty", text: activity.items.length ? "No calls on this page match your search." : "No calls match these filters." }));
    else visible.forEach(function (call) { list.appendChild(activityItem(call)); });
    var start = activity.total ? activity.offset + 1 : 0;
    var end = Math.min(activity.offset + activity.items.length, activity.total);
    $("activity-scope").textContent = activity.query ? "Search is limited to this page of calls." : "Showing " + start + "–" + end + " of " + activity.total + " calls matching these filters.";
    $("activity-page-count").textContent = visible.length === activity.items.length ? "Page contains " + activity.items.length + (activity.items.length === 1 ? " call" : " calls") : visible.length + " matching this page search";
    $("activity-prev").disabled = activity.loading || activity.offset <= 0;
    $("activity-next").disabled = activity.loading || activity.offset + activity.items.length >= activity.total;
    $("activity-next").hidden = activity.total <= PAGE_SIZE;
    $("activity-prev").hidden = activity.total <= PAGE_SIZE;
    list.setAttribute("aria-busy", activity.loading ? "true" : "false");
  }

  function loadActivity(reset) {
    if (activity.loading) {
      if (reset) activity.offset = 0;
      activity.reload = true;
      return;
    }
    if (reset) activity.offset = 0;
    activity.loading = true;
    var id = ++activity.request;
    renderActivity();
    requestJson(activityParams()).then(function (page) {
      if (!page || id !== activity.request) return;
      activity.items = Array.isArray(page.items) ? page.items : [];
      activity.total = Number(page.total) || 0;
      $("error-slot").replaceChildren();
    }).catch(function () {
      if (id !== activity.request) return;
      var retry = el("button", { cls: "btn", text: "Retry", attrs: { type: "button" } });
      retry.addEventListener("click", function () { loadActivity(false); });
      $("error-slot").replaceChildren(el("div", { cls: "banner", attrs: { role: "alert" } }, el("span", { text: "Couldn’t load call activity. Check your connection and retry." }), retry));
    }).then(function () {
      if (id !== activity.request) return;
      activity.loading = false;
      if (activity.reload) {
        activity.reload = false;
        loadActivity(false);
        return;
      }
      renderActivity();
    });
  }

  $("applicant-search").addEventListener("input", function (event) { directory.query = event.target.value.toLocaleLowerCase(); renderDirectory(); });
  $("applicant-status-filter").addEventListener("click", function (event) {
    var button = event.target.closest("button[data-status]");
    if (!button) return;
    directory.status = button.getAttribute("data-status");
    $("applicant-status-filter").querySelectorAll("button").forEach(function (item) { item.setAttribute("aria-pressed", String(item === button)); });
    renderDirectory();
  });
  $("applicants-refresh").addEventListener("click", function () { loadDirectory(true); });
  $("applicants-more").addEventListener("click", function () { loadDirectory(false); });

  $("applicant-readiness").addEventListener("change", function (event) { directory.readiness = event.target.value; renderDirectory(); });

  ["activity-review", "activity-sync", "activity-follow-up", "activity-day", "activity-sort"].forEach(function (id) {
    $(id).addEventListener("change", function () { loadActivity(true); });
  });
  $("activity-refresh").addEventListener("click", function () { loadActivity(false); });
  $("activity-prev").addEventListener("click", function () { activity.offset = Math.max(0, activity.offset - PAGE_SIZE); loadActivity(false); });
  $("activity-next").addEventListener("click", function () { activity.offset += PAGE_SIZE; loadActivity(false); });

  var activitySearch = el("input", { cls: "input activity-search-input", attrs: { type: "search", placeholder: "Search this page", "aria-label": "Search calls on this page" } });
  activitySearch.addEventListener("input", function () { activity.query = activitySearch.value.toLocaleLowerCase().trim(); renderActivity(); });
  var activitySearchWrap = el("label", { cls: "search-field activity-search" }, Desk.icon("search", "search-icon"), activitySearch);
  document.querySelector(".activity-toolbar").appendChild(activitySearchWrap);

  // The address is the source of truth for a page's filters: a link such as #applicants?status=to_call sets them,
  // and a plain link (no filters) puts them back to "everything".
  function applyApplicantFilters(params) {
    directory.status = params.status || "all";
    directory.readiness = params.readiness || "";
    $("applicant-readiness").value = directory.readiness;
    $("applicant-status-filter").querySelectorAll("button").forEach(function (item) {
      item.setAttribute("aria-pressed", String(item.getAttribute("data-status") === directory.status));
    });
  }

  function applyActivityFilters(params) {
    var wanted = { "activity-review": params.review || "", "activity-sync": params.sync || "",
                   "activity-follow-up": params.follow_up || "", "activity-day": params.day || "" };
    var changed = false;
    Object.keys(wanted).forEach(function (id) {
      if ($(id).value !== wanted[id]) { $(id).value = wanted[id]; changed = true; }
    });
    return changed;
  }

  function showRoute(route, params) {
    if (route === "applicants") {
      applyApplicantFilters(params);
      if (!directory.calls.length && !directory.loading) loadDirectory(false);
      else renderDirectory();
    }
    if (route === "activity") {
      var changed = applyActivityFilters(params);
      if (changed || (!activity.items.length && !activity.loading)) {
        if (activity.loading) { activity.offset = 0; activity.reload = true; }
        else loadActivity(true);
      }
    }
  }

  window.addEventListener("desk:route", function (event) { showRoute(event.detail.route, event.detail.params || {}); });

  // The first route event fired before this script loaded, so apply the address once now.
  var firstRoute = window.routeFilters ? window.routeFilters.parse(window.location.hash) : { route: Desk.currentRoute, params: {} };
  showRoute(Desk.currentRoute, firstRoute.route === Desk.currentRoute ? firstRoute.params : {});
})();
