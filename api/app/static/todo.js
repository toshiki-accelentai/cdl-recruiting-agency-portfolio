(function () {
  "use strict";

  var Desk = window.Desk;
  var $ = Desk.$, el = Desk.el, phoneText = Desk.phoneText, timeText = Desk.timeText, whenText = Desk.whenText;
  var agoText = Desk.agoText, clip = Desk.clip, toLogin = Desk.toLogin, toast = Desk.toast;
  var heatChip = Desk.heatChip, phoneLink = Desk.phoneLink;

  var REFRESH_MS = 60 * 1000;
  var STATUS_WORD = { called: "called", no_answer: "no answer", done: "done" };
  var REVIEW_REASON = {
    invalid_phone: "The phone number couldn't be used, so no applicant was created.",
    missing_name: "The caller never gave a name.",
    no_intake: "The call ended before the agent saved any details.",
  };
  var ROW_MOTION_MS = 300; // a bit longer than the CSS transition, so the row is removed after it finished
  // hidden: ids that left the screen on purpose (even if a refresh still lists them for a moment)
  // inflight: ids with a save running, so a second click cannot start another one
  // removed: the last row we removed, kept for Undo
  // version: bumped by every local change; a refresh that started before a change is out of date and is dropped
  var state = { data: null, sig: "", version: 0, timer: null, hidden: Object.create(null), inflight: Object.create(null), removed: Object.create(null) };

  function fact(key, value) {
    if (!value) return null;
    return el("span", {}, key ? el("span", { cls: "k", text: key }) : null, document.createTextNode(value));
  }

  // ---- attention rows (one per call) ------------------------------------------------------

  function attentionRow(call) {
    var failed = call.sync && call.sync.status === "failed";
    var who = call.applicant && call.applicant.name ? call.applicant.name : "Unknown caller";
    var badge = failed
      ? el("span", { cls: "chip chip-danger", text: "Zoho sync failed" })
      : el("span", { cls: "chip chip-warn", text: "Needs review" });

    var nameNode = call.applicant && call.applicant.id
      ? el("a", { cls: "attn-name name-link", text: who, attrs: { href: "/applicants/" + call.applicant.id } })
      : el("span", { cls: "attn-name", text: who });
    var body = el("div", {}, el("div", {}, nameNode));
    var phone = (call.applicant && call.applicant.phone) || call.caller_number;
    if (phone) body.appendChild(phoneLink(phone));

    if (failed) {
      var tries = call.sync.attempts + (call.sync.attempts === 1 ? " try" : " tries");
      var detail = "Saved here, not in Zoho yet. " + tries + ".";
      if (call.sync.last_error) detail += " " + clip(call.sync.last_error, 140);
      body.appendChild(el("p", { cls: "attn-detail", text: detail }));
      body.appendChild(el("p", { cls: "attn-hint", text: "Until it syncs, add this person in Zoho by hand with the same phone number." }));
    } else {
      body.appendChild(el("p", { cls: "attn-detail", text: REVIEW_REASON[call.review_reason] || "A recruiter should check this call." }));
    }

    if (!(call.applicant && call.applicant.id)) {
      if (call.summary) body.appendChild(el("p", { cls: "attn-summary", text: clip(call.summary, 280) }));
      if (call.has_recording) {
        body.appendChild(el("audio", { cls: "attn-audio", attrs: { controls: "", preload: "none", src: "/api/calls/" + call.id + "/recording", "aria-label": "Call recording" } }));
      }
    }

    var when = el("span", { cls: "attn-when", text: agoText(call.created_at), attrs: { title: whenText(call.created_at) } });
    return el("li", { cls: "attn" }, el("div", {}, badge), body, when);
  }

  // ---- call back rows (one per person) ----------------------------------------------------

  function whenCell(row) {
    var cell = el("div", { cls: "c-when" }, el("div", { cls: "when-label", text: "Callback time" }));
    if (!row.preferred_callback_at) {
      cell.appendChild(el("div", { cls: "when-value is-none", text: "None given" }));
      return cell;
    }
    var late = new Date(row.preferred_callback_at).getTime() < Date.now();
    cell.appendChild(el("div", { cls: "when-value" + (late ? " is-late" : ""), text: (late ? "Was due " : "") + whenText(row.preferred_callback_at) }));
    return cell;
  }

  function actionButton(label, status, person) {
    var button = el("button", { text: label, attrs: { type: "button", "aria-label": "Mark " + person.name + " as " + STATUS_WORD[status] } });
    button.addEventListener("click", function () { markFollowUp(person, status); });
    return button;
  }

  function callBackRow(row, rank) {
    var person = row.applicant;
    var status = person.follow_up && person.follow_up.status;
    var nameLine = el("div", { cls: "name-line" },
      el("a", { cls: "name name-link", text: person.name || "No name given", attrs: { href: "/applicants/" + person.id } }),
      heatChip(person.temperature));
    // Everyone in this list is waiting for contact, so only a different status is worth a chip.
    if (status && status !== "to_call") nameLine.appendChild(Desk.followUpChip(status));
    if (row.new_call_since) nameLine.appendChild(el("span", { cls: "chip chip-accent", text: "Called again" }));
    if (row.call_count > 1) nameLine.appendChild(el("span", { cls: "faint", text: row.call_count + " calls" }));

    var phoneLine = el("div", { cls: "phone-line" }, phoneLink(person.phone));
    if (person.callback_phone) {
      phoneLine.appendChild(el("span", { cls: "also" }, document.createTextNode("Call back at "), phoneLink(person.callback_phone, "")));
    }

    var place = [person.city, person.state].filter(Boolean).join(", ");
    var facts = el("div", { cls: "facts" }, fact(null, place), fact(null, person.experience), fact("Ready", person.readiness));

    var main = el("div", { cls: "c-main" }, nameLine, phoneLine, facts);
    var note = person.follow_up && person.follow_up.note;
    if (note) main.appendChild(el("p", { cls: "note", text: "Note: " + clip(note, 200) }));

    var seg = el("div", { cls: "seg", attrs: { role: "group", "aria-label": "Follow-up for " + person.name } },
      actionButton("Called", "called", person), actionButton("No answer", "no_answer", person), actionButton("Done", "done", person));

    var rankNode = el("span", { cls: "queue-rank c-rank", text: String(rank || 1), attrs: { "aria-label": "Queue position " + (rank || 1) } });
    var item = el("li", { cls: "row", attrs: { "data-applicant": String(person.id) } }, rankNode, main, whenCell(row), el("div", { cls: "c-act" }, seg));
    return item;
  }

  function refreshQueueRanks() {
    var rows = Array.prototype.slice.call(document.querySelectorAll("#callback-list .row:not(.is-leaving)"));
    rows.forEach(function (item, index) {
      var rank = index + 1;
      var rankNode = item.querySelector(".queue-rank");
      if (rankNode) {
        rankNode.textContent = String(rank);
        rankNode.setAttribute("aria-label", "Queue position " + rank);
      }
      item.classList.toggle("priority-first", rank === 1);
    });
  }

  // ---- render -----------------------------------------------------------------------------

  function emptyState(title, body) {
    return el("li", { cls: "empty" }, el("p", { cls: "empty-title", text: title }), el("p", { cls: "empty-body", text: body }));
  }

  function allCaughtUp() {
    return emptyState("You're all caught up", "New applicants appear here as soon as the agent saves a call.");
  }

  function visibleCallBack(data) {
    return data.call_back.filter(function (row) { return !state.hidden[row.applicant.id]; });
  }

  var READINESS_ORDER = { HOT: 0, MEDIUM: 1, WARM: 2, COLD: 3 };

  function comparePriority(a, b) {
    var aTime = a.preferred_callback_at ? new Date(a.preferred_callback_at).getTime() : Infinity;
    var bTime = b.preferred_callback_at ? new Date(b.preferred_callback_at).getTime() : Infinity;
    if (aTime !== bTime) return aTime - bTime;
    var aReady = READINESS_ORDER[a.applicant.temperature] == null ? 4 : READINESS_ORDER[a.applicant.temperature];
    var bReady = READINESS_ORDER[b.applicant.temperature] == null ? 4 : READINESS_ORDER[b.applicant.temperature];
    if (aReady !== bReady) return aReady - bReady;
    return Number(a.applicant.id) - Number(b.applicant.id);
  }

  function priorityText(row) {
    if (!row) return null;
    if (!row.preferred_callback_at) return { badge: "No time set", detail: "No callback time was recorded. Check the applicant’s preferred time before calling." };
    var delta = new Date(row.preferred_callback_at).getTime() - Date.now();
    if (delta < 0) return { badge: "Overdue", detail: "Requested callback " + whenText(row.preferred_callback_at) + "." };
    if (delta <= 60 * 60 * 1000) return { badge: "Due soon", detail: "Requested callback " + whenText(row.preferred_callback_at) + "." };
    return { badge: "Scheduled", detail: "Requested callback " + whenText(row.preferred_callback_at) + "." };
  }

  function renderPriority(data) {
    var rows = visibleCallBack(data).slice().sort(comparePriority);
    var next = rows[0];
    var after = rows[1];
    var reason = $("next-reason");
    var action = $("next-action");
    action.classList.toggle("has-overdue", Boolean(next && next.preferred_callback_at && new Date(next.preferred_callback_at).getTime() < Date.now()));
    if (next) {
      var priority = priorityText(next);
      reason.className = "urgent-reason" + (priority.badge === "Overdue" || priority.badge === "Due soon" ? "" : " is-neutral");
      $("next-name").textContent = next.applicant.name || "No name given";
      $("next-detail").textContent = priority.detail;
      reason.textContent = priority.badge;
      reason.hidden = false;
      $("next-link").href = "/applicants/" + next.applicant.id;
    } else {
      $("next-name").textContent = "No callbacks waiting";
      $("next-detail").textContent = "New applicants will appear here when a call is saved.";
      reason.textContent = "All caught up";
      reason.className = "urgent-reason is-neutral";
      reason.hidden = false;
      $("next-link").href = "/#applicants";
    }
    if (after) {
      var person = after.applicant;
      $("after-name").textContent = person.name || "No name given";
      $("after-time").textContent = after.preferred_callback_at ? whenText(after.preferred_callback_at) : "No time requested";
      $("after-link").href = "/applicants/" + person.id;
      $("after-link").setAttribute("aria-label", "Review " + (person.name || "applicant") + ", second in callback queue");
    } else {
      $("after-name").textContent = rows.length ? "No one after this" : "Queue is clear";
      $("after-time").textContent = rows.length ? "Only one applicant is waiting" : "No callback requests are waiting";
      $("after-link").href = "/#applicants";
    }
  }

  // What the lists contain. If a refresh brings the same lists, nothing is redrawn (no flicker).
  function signature(data) { return JSON.stringify([data.attention, data.call_back]); }

  // The numbers follow what is on screen: a row that already left counts as gone.
  function applyCounts(data) {
    var rows = visibleCallBack(data);
    var summary = Object.assign({}, data.summary, {
      to_call: rows.length,
      hot_waiting: rows.filter(function (row) { return row.applicant.temperature === "HOT"; }).length,
    });
    document.querySelectorAll("[data-stat]").forEach(function (node) { node.textContent = String(summary[node.dataset.stat]); });
    $("stat-sync").classList.toggle("is-problem", summary.sync_problems > 0);
    // Hang-ups from unknown callers are only counted, so they never push a real problem down the list.
    var hangUps = Number(summary.hang_ups_today) || 0;
    $("hang-ups-note").hidden = hangUps === 0;
    $("hang-ups-word").textContent = hangUps === 1 ? "hang-up" : "hang-ups";
    $("callback-count").textContent = String(rows.length);
    var total = rows.length + data.attention.length;
    if (Desk.currentRoute === "overview") document.title = (total ? "(" + total + ") " : "") + "Overview | Frontline CDL";
    $("updated").textContent = "Updated " + timeText(new Date());
    renderPriority(data);
    refreshQueueRanks();
  }

  function render(data) {
    var attentionList = $("attention-list");
    attentionList.replaceChildren();
    data.attention.forEach(function (call) { attentionList.appendChild(attentionRow(call)); });
    $("attention-section").hidden = data.attention.length === 0;
    $("attention-count").textContent = String(data.attention.length);

    var rows = visibleCallBack(data);
    var list = $("callback-list");
    list.replaceChildren();
    if (rows.length === 0) list.appendChild(allCaughtUp());
    else rows.forEach(function (row, index) { list.appendChild(callBackRow(row, index + 1)); });
    refreshQueueRanks();
    list.setAttribute("aria-busy", "false");
    applyCounts(data);
    $("error-slot").replaceChildren();
  }

  function renderSkeleton() {
    var list = $("callback-list");
    list.replaceChildren();
    for (var i = 0; i < 3; i++) list.appendChild(el("li", { cls: "skeleton" }));
  }

  function showLoadError() {
    var retry = el("button", { cls: "btn", text: "Retry", attrs: { type: "button" } });
    retry.addEventListener("click", load);
    $("error-slot").replaceChildren(el("div", { cls: "banner", attrs: { role: "alert" } },
      el("span", { text: "Couldn't load your to do list. Check your connection and retry." }), retry));
    $("callback-list").setAttribute("aria-busy", "false");
  }

  // ---- row motion: a row closes (or opens) smoothly; nothing else on the page is redrawn -----

  function rowFor(id) { return document.querySelector('#callback-list [data-applicant="' + id + '"]'); }

  function removeRow(id) {
    var li = rowFor(id);
    if (!li) return;
    var list = li.parentNode;
    if (li.contains(document.activeElement)) { // keep the keyboard place: move focus to the next row
      var neighbour = li.nextElementSibling || li.previousElementSibling;
      var target = neighbour && neighbour.querySelector("button, a");
      if (!target) { target = $("callback-title"); target.setAttribute("tabindex", "-1"); }
      target.focus({ preventScroll: true });
    }
    li.querySelectorAll("button, a").forEach(function (node) { node.tabIndex = -1; });
    li.style.height = li.offsetHeight + "px"; // from a fixed height, so it can animate to 0
    void li.offsetHeight;
    li.classList.add("is-leaving");
    li.style.height = "0px";
    refreshQueueRanks();
    window.setTimeout(function () {
      li.remove();
      if (!list.querySelector(".row")) list.appendChild(allCaughtUp());
    }, ROW_MOTION_MS);
  }

  // dataIndex is the row's place in state.data.call_back, which already contains it
  function insertRow(rowData, dataIndex) {
    var list = $("callback-list");
    var empty = list.querySelector(".empty");
    if (empty) empty.remove();
    var old = rowFor(rowData.applicant.id);
    if (old) old.remove();
    var currentRows = visibleCallBack(state.data);
    var rank = currentRows.findIndex(function (row) { return row.applicant.id === rowData.applicant.id; }) + 1;
    var li = callBackRow(rowData, rank);
    var before = null;
    var rows = state.data.call_back;
    for (var i = dataIndex + 1; i < rows.length && !before; i++) {
      var next = rowFor(rows[i].applicant.id);
      if (next && !next.classList.contains("is-leaving")) before = next;
    }
    list.insertBefore(li, before);
    refreshQueueRanks();
    var natural = li.offsetHeight;
    li.style.height = "0px";
    li.classList.add("is-entering");
    void li.offsetHeight;
    li.classList.remove("is-entering");
    li.style.height = natural + "px";
    window.setTimeout(function () { li.style.height = ""; }, ROW_MOTION_MS);
  }

  // ---- data -------------------------------------------------------------------------------

  function load() {
    var startedAt = state.version;
    return fetch("/api/todo", { headers: { Accept: "application/json" } }).then(function (response) {
      if (response.status === 401) { toLogin(); return null; }
      if (!response.ok) throw new Error("status " + response.status);
      return response.json();
    }).then(function (data) {
      if (!data) return;
      // Out of date (we changed something after it started) or a save is running: the server may not know
      // yet, so this answer could undo what the screen shows. Drop it; the next refresh will be right.
      if (startedAt !== state.version || Object.keys(state.inflight).length) return;
      Object.keys(state.hidden).forEach(function (id) { // the server caught up: no need to keep hiding it
        if (!data.call_back.some(function (row) { return String(row.applicant.id) === id; })) delete state.hidden[id];
      });
      data.call_back.sort(comparePriority);
      var changed = signature(data) !== state.sig;
      state.data = data;
      state.sig = signature(data);
      if (changed) render(data);
      else { applyCounts(data); $("error-slot").replaceChildren(); }
    }).catch(function () {
      if (!state.data) { $("callback-list").replaceChildren(); }
      showLoadError();
    });
  }

  function patchFollowUp(id, status) {
    return fetch("/api/applicants/" + id + "/follow-up", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: status }),
    }).then(function (response) {
      if (response.status === 401) { toLogin(); throw new Error("signed out"); }
      if (!response.ok) throw new Error("status " + response.status);
    });
  }

  // our copy of the list: drop a row, so the next refresh sees the same lists and redraws nothing
  function forget(id) {
    state.data.call_back = state.data.call_back.filter(function (row) { return row.applicant.id !== id; });
    state.sig = signature(state.data);
  }

  // put a row back into our copy of the list (never twice) and return where it went
  function putBack(rowData, index) {
    state.data.call_back = state.data.call_back.filter(function (row) { return row.applicant.id !== rowData.applicant.id; });
    var at = Math.min(index, state.data.call_back.length);
    state.data.call_back.splice(at, 0, rowData);
    state.sig = signature(state.data);
    return at;
  }

  // Optimistic: the row closes at once, the save runs in the background. If the save fails, the row comes back.
  function markFollowUp(person, status) {
    var id = person.id;
    if (state.inflight[id]) return;
    var index = state.data.call_back.findIndex(function (row) { return row.applicant.id === id; });
    if (index < 0) return;
    var rowData = state.data.call_back[index];
    state.version++;
    state.inflight[id] = true;
    state.hidden[id] = true;
    removeRow(id);
    applyCounts(state.data);

    patchFollowUp(id, status).then(function () {
      forget(id);
      state.removed[id] = { row: rowData, index: index };
      toast("Marked " + person.name + " as " + STATUS_WORD[status] + ".", "Undo", function () { undoFollowUp(id); });
    }).catch(function () {
      delete state.hidden[id];
      insertRow(rowData, putBack(rowData, index));
      applyCounts(state.data);
      toast("Couldn't save that. Nothing was changed.", null);
    }).then(function () { state.version++; delete state.inflight[id]; });
  }

  function undoFollowUp(id) {
    var record = state.removed[id];
    if (!record || state.inflight[id]) { load(); return; }
    state.version++;
    state.inflight[id] = true;
    var at = putBack(record.row, record.index);
    delete state.hidden[id];
    insertRow(record.row, at);
    applyCounts(state.data);

    patchFollowUp(id, "to_call").then(function () {
      delete state.removed[id];
    }).catch(function () {
      forget(id);
      state.hidden[id] = true;
      removeRow(id);
      applyCounts(state.data);
      toast("Couldn't undo. Try again from the list.", null);
    }).then(function () { state.version++; delete state.inflight[id]; });
  }

  // ---- boot -------------------------------------------------------------------------------

  $("today").textContent = new Intl.DateTimeFormat("en-US", { timeZone: Desk.TZ, weekday: "long", month: "long", day: "numeric" }).format(new Date());

  renderSkeleton();
  load();
  state.timer = window.setInterval(load, REFRESH_MS);
  document.addEventListener("visibilitychange", function () { if (!document.hidden) load(); });
})();
