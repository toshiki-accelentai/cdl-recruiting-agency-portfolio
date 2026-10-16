(function () {
  "use strict";

  var TZ = "America/Vancouver"; // the agency's business time zone
  var REFRESH_MS = 60 * 1000;
  var TOAST_MS = 7000;

  var HEAT = {
    HOT: { label: "Hot", bars: 4, chip: "chip-danger" },
    MEDIUM: { label: "Medium", bars: 3, chip: "chip-warn" },
    WARM: { label: "Warm", bars: 2, chip: "chip-calm" },
    COLD: { label: "Cold", bars: 1, chip: "chip-calm" },
  };
  var STATUS_WORD = { called: "called", no_answer: "no answer", done: "done" };
  var REVIEW_REASON = {
    invalid_phone: "The phone number couldn't be used, so no applicant was created.",
    missing_name: "The caller never gave a name.",
  };

  var $ = function (id) { return document.getElementById(id); };
  var state = { data: null, timer: null, busy: Object.create(null) };

  // ---- tiny DOM helper: text only, never HTML --------------------------------------------

  function el(tag, props) {
    var node = document.createElement(tag);
    props = props || {};
    if (props.cls) node.className = props.cls;
    if (props.text != null) node.textContent = props.text;
    if (props.attrs) Object.keys(props.attrs).forEach(function (k) { node.setAttribute(k, props.attrs[k]); });
    for (var i = 2; i < arguments.length; i++) {
      if (arguments[i]) node.appendChild(arguments[i]);
    }
    return node;
  }

  // ---- formatting -------------------------------------------------------------------------

  function phoneText(e164) {
    var m = /^\+1(\d{3})(\d{3})(\d{4})$/.exec(e164 || "");
    return m ? "(" + m[1] + ") " + m[2] + "-" + m[3] : e164 || "";
  }

  function dayKey(date) {
    return new Intl.DateTimeFormat("en-CA", { timeZone: TZ }).format(date); // 2026-10-15
  }

  function timeText(date) {
    return new Intl.DateTimeFormat("en-US", { timeZone: TZ, hour: "numeric", minute: "2-digit" }).format(date);
  }

  function whenText(iso) {
    var date = new Date(iso);
    var today = new Date();
    var dayMs = 24 * 60 * 60 * 1000;
    var key = dayKey(date);
    var label;
    if (key === dayKey(today)) label = "Today";
    else if (key === dayKey(new Date(today.getTime() + dayMs))) label = "Tomorrow";
    else if (key === dayKey(new Date(today.getTime() - dayMs))) label = "Yesterday";
    else label = new Intl.DateTimeFormat("en-US", { timeZone: TZ, weekday: "short", month: "short", day: "numeric" }).format(date);
    return label + ", " + timeText(date);
  }

  function agoText(iso) {
    var seconds = Math.round((new Date(iso).getTime() - Date.now()) / 1000);
    var rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
    var abs = Math.abs(seconds);
    if (abs < 60) return "just now";
    if (abs < 3600) return rtf.format(Math.round(seconds / 60), "minute");
    if (abs < 86400) return rtf.format(Math.round(seconds / 3600), "hour");
    return rtf.format(Math.round(seconds / 86400), "day");
  }

  function clip(text, max) {
    return text && text.length > max ? text.slice(0, max - 1) + "..." : text || "";
  }

  // ---- pieces -----------------------------------------------------------------------------

  function heatChip(temperature) {
    var spec = HEAT[temperature] || HEAT.COLD;
    var bars = el("span", { cls: "heat", attrs: { "aria-hidden": "true" } });
    for (var i = 1; i <= 4; i++) bars.appendChild(el("i", { cls: i <= spec.bars ? "on" : "" }));
    return el("span", { cls: "chip " + spec.chip }, bars, el("span", { text: spec.label }));
  }

  function phoneLink(e164, extraCls) {
    return el("a", { cls: "phone mono" + (extraCls ? " " + extraCls : ""), text: phoneText(e164), attrs: { href: "tel:" + e164 } });
  }

  function fact(key, value) {
    if (!value) return null;
    return el("span", {}, el("span", { cls: "k", text: key }), document.createTextNode(value));
  }

  // ---- attention rows (one per call) ------------------------------------------------------

  function attentionRow(call) {
    var failed = call.sync && call.sync.status === "failed";
    var who = call.applicant && call.applicant.name ? call.applicant.name : "Unknown caller";
    var badge = failed
      ? el("span", { cls: "chip chip-danger", text: "Zoho sync failed" })
      : el("span", { cls: "chip chip-warn", text: "Needs review" });

    var body = el("div", {}, el("div", { cls: "attn-name", text: who }));
    if (call.applicant && call.applicant.phone) body.appendChild(phoneLink(call.applicant.phone));

    if (failed) {
      var tries = call.sync.attempts + (call.sync.attempts === 1 ? " try" : " tries");
      var detail = "Saved here, not in Zoho yet. " + tries + ".";
      if (call.sync.last_error) detail += " " + clip(call.sync.last_error, 140);
      body.appendChild(el("p", { cls: "attn-detail", text: detail }));
      body.appendChild(el("p", { cls: "attn-hint", text: "Until it syncs, add this person in Zoho by hand with the same phone number." }));
    } else {
      body.appendChild(el("p", { cls: "attn-detail", text: REVIEW_REASON[call.review_reason] || "A recruiter should check this call." }));
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

  function callBackRow(row) {
    var person = row.applicant;
    var nameLine = el("div", { cls: "name-line" }, el("span", { cls: "name", text: person.name || "No name given" }));
    if (row.new_call_since) nameLine.appendChild(el("span", { cls: "chip chip-accent", text: "Called again" }));
    if (row.call_count > 1) nameLine.appendChild(el("span", { cls: "faint", text: row.call_count + " calls" }));

    var phoneLine = el("div", {}, phoneLink(person.phone));
    if (person.callback_phone) {
      phoneLine.appendChild(el("span", { cls: "also" }, document.createTextNode("Call back at "), phoneLink(person.callback_phone, "")));
    }

    var place = [person.city, person.state].filter(Boolean).join(", ");
    var facts = el("div", { cls: "facts" }, fact("Location", place), fact("Experience", person.experience), fact("Ready", person.readiness));

    var main = el("div", { cls: "c-main" }, nameLine, phoneLine, facts);
    var note = person.follow_up && person.follow_up.note;
    if (note) main.appendChild(el("p", { cls: "note", text: "Note: " + clip(note, 200) }));

    var seg = el("div", { cls: "seg", attrs: { role: "group", "aria-label": "Follow-up for " + person.name } },
      actionButton("Called", "called", person), actionButton("No answer", "no_answer", person), actionButton("Done", "done", person));

    var item = el("li", { cls: "row", attrs: { "data-applicant": String(person.id) } },
      el("div", { cls: "c-heat" }, heatChip(person.temperature)), main, whenCell(row), el("div", { cls: "c-act" }, seg));
    return item;
  }

  // ---- render -----------------------------------------------------------------------------

  function emptyState(title, body) {
    return el("li", { cls: "empty" }, el("p", { cls: "empty-title", text: title }), el("p", { cls: "empty-body", text: body }));
  }

  function render(data) {
    var summary = data.summary;
    document.querySelectorAll("[data-stat]").forEach(function (node) { node.textContent = String(summary[node.dataset.stat]); });
    $("stat-sync").classList.toggle("is-problem", summary.sync_problems > 0);

    var attentionList = $("attention-list");
    attentionList.replaceChildren();
    data.attention.forEach(function (call) { attentionList.appendChild(el("li", {}, attentionRow(call))); });
    $("attention-section").hidden = data.attention.length === 0;
    $("attention-count").textContent = String(data.attention.length);

    var list = $("callback-list");
    list.replaceChildren();
    if (data.call_back.length === 0) {
      list.appendChild(emptyState("You're all caught up", "New applicants appear here as soon as the agent saves a call."));
    } else {
      data.call_back.forEach(function (row) { list.appendChild(callBackRow(row)); });
    }
    list.setAttribute("aria-busy", "false");
    $("callback-count").textContent = String(data.call_back.length);

    document.title = (data.call_back.length + data.attention.length ? "(" + (data.call_back.length + data.attention.length) + ") " : "") + "To do | Frontline CDL";
    $("updated").textContent = "Updated " + timeText(new Date());
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

  // ---- data -------------------------------------------------------------------------------

  function toLogin() { window.location.assign("/login"); }

  function load() {
    return fetch("/api/todo", { headers: { Accept: "application/json" } }).then(function (response) {
      if (response.status === 401) { toLogin(); return null; }
      if (!response.ok) throw new Error("status " + response.status);
      return response.json();
    }).then(function (data) {
      if (!data) return;
      state.data = data;
      render(data);
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

  function markFollowUp(person, status) {
    if (state.busy[person.id]) return;
    state.busy[person.id] = true;
    var row = document.querySelector('[data-applicant="' + person.id + '"]');
    if (row) row.querySelectorAll("button").forEach(function (b) { b.disabled = true; });

    patchFollowUp(person.id, status).then(function () {
      if (row) row.classList.add("is-leaving");
      window.setTimeout(load, 260);
      toast("Marked " + person.name + " as " + STATUS_WORD[status] + ".", "Undo", function () {
        patchFollowUp(person.id, "to_call").then(load).catch(function () { toast("Couldn't undo. Try again from the list.", null); });
      });
    }).catch(function () {
      if (row) row.querySelectorAll("button").forEach(function (b) { b.disabled = false; });
      toast("Couldn't save that. Nothing was changed.", null);
    }).then(function () { delete state.busy[person.id]; });
  }

  // ---- toast ------------------------------------------------------------------------------

  function toast(message, actionLabel, onAction) {
    var node = el("div", { cls: "toast" }, el("span", { text: message }));
    var timer = window.setTimeout(remove, TOAST_MS);
    function remove() { window.clearTimeout(timer); node.remove(); }
    if (actionLabel) {
      var button = el("button", { cls: "btn", text: actionLabel, attrs: { type: "button" } });
      button.addEventListener("click", function () { remove(); onAction(); });
      node.appendChild(button);
    }
    $("toasts").replaceChildren(node);
  }

  // ---- boot -------------------------------------------------------------------------------

  $("today").textContent = new Intl.DateTimeFormat("en-US", { timeZone: TZ, weekday: "long", month: "long", day: "numeric" }).format(new Date());

  $("signout").addEventListener("click", function () {
    fetch("/logout", { method: "POST" }).then(toLogin, toLogin);
  });

  fetch("/api/me").then(function (r) { return r.ok ? r.json() : null; }).then(function (me) {
    if (me) $("who").textContent = me.username;
  }).catch(function () {});

  renderSkeleton();
  load();
  state.timer = window.setInterval(load, REFRESH_MS);
  document.addEventListener("visibilitychange", function () { if (!document.hidden) load(); });
})();
