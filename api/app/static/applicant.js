(function () {
  "use strict";

  var Desk = window.Desk;
  var $ = Desk.$, el = Desk.el, whenText = Desk.whenText, agoText = Desk.agoText, clip = Desk.clip;
  var phoneText = Desk.phoneText, phoneLink = Desk.phoneLink, heatChip = Desk.heatChip;
  var toLogin = Desk.toLogin, toast = Desk.toast;

  var match = /^\/applicants\/(\d+)/.exec(window.location.pathname);
  var applicantId = match ? match[1] : null;

  var FOLLOW_UP = [
    { status: "to_call", label: "To call" },
    { status: "called", label: "Called" },
    { status: "no_answer", label: "No answer" },
    { status: "done", label: "Done" },
  ];
  var STATUS_LABEL = { to_call: "to call", called: "called", no_answer: "no answer", done: "done" };
  var REVIEW_REASON = {
    invalid_phone: "The phone number couldn't be used.",
    missing_name: "The caller never gave a name.",
  };
  var FIELD_LABEL = {
    name: "name", phone: "phone", city: "city", state: "state", zip_code: "ZIP code",
    experience: "experience", readiness: "readiness", temperature: "temperature",
  };
  var TEMPERATURES = [["HOT", "Hot"], ["MEDIUM", "Medium"], ["WARM", "Warm"], ["COLD", "Cold"]];

  // The editable profile fields: key, label, input attributes.
  var FIELDS = [
    { key: "name", label: "Name", attrs: { maxlength: "100", autocomplete: "off" } },
    { key: "phone", label: "Phone", attrs: { inputmode: "tel", autocomplete: "off" } },
    { key: "city", label: "City", attrs: { maxlength: "100" } },
    { key: "state", label: "State", attrs: { maxlength: "2", autocapitalize: "characters" } },
    { key: "zip_code", label: "ZIP code", attrs: { maxlength: "10", inputmode: "numeric" } },
    { key: "experience", label: "Experience", attrs: { maxlength: "100" } },
    { key: "readiness", label: "Ready to start", attrs: { maxlength: "100" } },
  ];

  var state = { data: null, editing: false, busy: false };

  // ---- loading ----------------------------------------------------------------------------

  function load() {
    return fetch("/api/applicants/" + applicantId, { headers: { Accept: "application/json" } }).then(function (response) {
      if (response.status === 401) { toLogin(); return null; }
      if (response.status === 404) { renderNotFound(); return null; }
      if (!response.ok) throw new Error("status " + response.status);
      return response.json();
    }).then(function (data) {
      if (!data) return;
      state.data = data;
      state.editing = false;
      $("error-slot").replaceChildren();
      render();
    }).catch(function () {
      var retry = el("button", { cls: "btn", text: "Retry", attrs: { type: "button" } });
      retry.addEventListener("click", load);
      $("error-slot").replaceChildren(el("div", { cls: "banner", attrs: { role: "alert" } },
        el("span", { text: "Couldn't load this applicant. Check your connection and retry." }), retry));
      $("content").setAttribute("aria-busy", "false");
    });
  }

  function request(method, url, body) {
    return fetch(url, {
      method: method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(function (response) {
      if (response.status === 401) { toLogin(); throw new Error("signed out"); }
      if (response.ok) return response.json();
      return response.json().catch(function () { return {}; }).then(function (payload) {
        var error = new Error("status " + response.status);
        error.status = response.status;
        error.detail = payload.detail;
        throw error;
      });
    });
  }

  // ---- pieces -----------------------------------------------------------------------------

  function renderNotFound() {
    $("crumb-name").textContent = "Not found";
    $("content").replaceChildren(el("div", { cls: "not-found" },
      el("h1", { text: "We couldn't find that applicant" }),
      el("p", { cls: "page-sub", text: "The link may be old, or the person was never saved." }),
      el("p", {}, el("a", { cls: "btn", text: "Back to To do", attrs: { href: "/" } }))));
    $("content").setAttribute("aria-busy", "false");
    document.title = "Not found | Frontline CDL";
  }

  function followUpControl(person) {
    var current = person.follow_up.status;
    var seg = el("div", { cls: "seg", attrs: { role: "group", "aria-label": "Follow-up status" } });
    FOLLOW_UP.forEach(function (option) {
      var button = el("button", { text: option.label, attrs: { type: "button", "aria-pressed": String(option.status === current) } });
      button.addEventListener("click", function () { setFollowUp(option.status, current); });
      seg.appendChild(button);
    });
    return seg;
  }

  function header(person) {
    var title = el("div", { cls: "detail-title" }, el("h1", { text: person.name || "No name given" }), heatChip(person.temperature));
    if (person.follow_up.new_call_since) title.appendChild(el("span", { cls: "chip chip-accent", text: "Called again" }));

    var place = [person.city, person.state].filter(Boolean).join(", ");
    var sub = el("div", { cls: "detail-sub" }, phoneLink(person.phone));
    if (person.callback_phone) sub.appendChild(el("span", {}, document.createTextNode("Call back at "), phoneLink(person.callback_phone)));
    if (place) sub.appendChild(el("span", { text: place }));

    return el("div", { cls: "detail-head" }, el("div", {}, title, sub), followUpControl(person));
  }

  // ---- calls ------------------------------------------------------------------------------

  function syncChip(call) {
    if (!call.sync) return null;
    var map = {
      sent: ["chip chip-calm", "Sent to Zoho"],
      pending: ["chip chip-warn", "Waiting to send"],
      failed: ["chip chip-danger", "Zoho sync failed"],
    };
    var spec = map[call.sync.status];
    return spec ? el("span", { cls: spec[0], text: spec[1] }) : null;
  }

  function callRow(call) {
    var chips = el("div", { cls: "call-chips" });
    if (call.needs_review) chips.appendChild(el("span", { cls: "chip chip-warn", text: "Needs review" }));
    chips.appendChild(syncChip(call));

    var row = el("li", { cls: "call-row" },
      el("div", { cls: "call-top" },
        el("span", { cls: "call-when", text: whenText(call.created_at), attrs: { title: agoText(call.created_at) } }), chips));

    if (call.preferred_callback_at) {
      row.appendChild(el("p", { cls: "call-line", text: "Asked to be called back " + whenText(call.preferred_callback_at) + "." }));
    }
    if (call.needs_review) {
      row.appendChild(el("p", { cls: "call-line", text: REVIEW_REASON[call.review_reason] || "A recruiter should check this call." }));
    }
    if (call.sync && call.sync.status === "failed") {
      var detail = "Saved here, not in Zoho yet. " + call.sync.attempts + (call.sync.attempts === 1 ? " try." : " tries.");
      if (call.sync.last_error) detail += " " + clip(call.sync.last_error, 140);
      row.appendChild(el("p", { cls: "call-line", text: detail }));
    }
    return row;
  }

  function callsSection(calls) {
    var list = el("ul", { cls: "rows" });
    calls.forEach(function (call) { list.appendChild(callRow(call)); });
    return el("section", { attrs: { "aria-labelledby": "calls-title" } },
      el("div", { cls: "section-head" }, el("h2", { text: "Calls", attrs: { id: "calls-title" } }), el("span", { cls: "count", text: String(calls.length) })),
      el("div", { cls: "panel" }, list));
  }

  // ---- profile (view and edit) ------------------------------------------------------------

  function viewValue(person, field) {
    if (field.key === "phone") return phoneText(person.phone);
    if (field.key === "state") return person.state;
    return person[field.key];
  }

  function profileView(person) {
    var box = el("div", { cls: "profile" });
    FIELDS.forEach(function (field) {
      var value = viewValue(person, field);
      var node = el("span", { cls: "v" + (field.key === "phone" ? " mono" : ""), text: value || "Not given" });
      if (!value) node.classList.add("faint");
      box.appendChild(el("div", { cls: "pf" }, el("span", { cls: "k", text: field.label }), node));
    });
    var temp = (TEMPERATURES.filter(function (t) { return t[0] === person.temperature; })[0] || ["", person.temperature])[1];
    box.appendChild(el("div", { cls: "pf" }, el("span", { cls: "k", text: "Temperature" }), el("span", { cls: "v", text: temp })));
    box.appendChild(el("div", { cls: "pf" }, el("span", { cls: "k", text: "Call back at" }),
      person.callback_phone ? phoneLink(person.callback_phone) : el("span", { cls: "v faint", text: "Not given" })));
    return box;
  }

  function profileForm(person) {
    var form = el("form", { attrs: { novalidate: "" } });
    var inputs = {};
    var box = el("div", { cls: "profile" });

    FIELDS.forEach(function (field) {
      var id = "f-" + field.key;
      var input = el("input", { cls: "input", attrs: Object.assign({ id: id, type: "text", "aria-label": field.label }, field.attrs) });
      input.value = field.key === "phone" ? phoneText(person.phone) : person[field.key] || "";
      inputs[field.key] = input;
      box.appendChild(el("div", { cls: "pf" }, el("label", { cls: "k", text: field.label, attrs: { for: id } }), input,
        el("span", { cls: "pf-error", attrs: { id: id + "-error", role: "alert" } })));
    });

    var select = el("select", { cls: "input", attrs: { id: "f-temperature", "aria-label": "Temperature" } });
    TEMPERATURES.forEach(function (t) { select.appendChild(el("option", { text: t[1], attrs: { value: t[0] } })); });
    select.value = person.temperature;
    inputs.temperature = select;
    box.appendChild(el("div", { cls: "pf" }, el("label", { cls: "k", text: "Temperature", attrs: { for: "f-temperature" } }), select));
    form.appendChild(box);
    form.appendChild(el("p", { cls: "help", text: "Temperature comes from how soon they can start. Change it if you know better." }));

    var formError = el("p", { cls: "form-error", attrs: { role: "alert" } });
    var cancel = el("button", { cls: "btn btn-sm", text: "Cancel", attrs: { type: "button" } });
    var save = el("button", { cls: "btn btn-primary btn-sm", text: "Save changes", attrs: { type: "submit" } });
    cancel.addEventListener("click", function () { state.editing = false; render(); });
    form.appendChild(formError);
    form.appendChild(el("div", { cls: "form-actions" }, cancel, save));

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      submitProfile(person, inputs, formError, save);
    });
    return form;
  }

  function fieldError(key, message) {
    var node = $("f-" + key + "-error");
    if (node) node.textContent = message;
    var input = $("f-" + key);
    if (input) { if (message) input.setAttribute("aria-invalid", "true"); else input.removeAttribute("aria-invalid"); }
  }

  function changedFields(person, inputs) {
    var changes = {};
    FIELDS.forEach(function (field) {
      var raw = inputs[field.key].value.trim();
      var before = field.key === "phone" ? person.phone : person[field.key] || "";
      var shownBefore = field.key === "phone" ? phoneText(person.phone) : before;
      if (raw !== before && raw !== shownBefore) changes[field.key] = raw;
    });
    if (inputs.temperature.value !== person.temperature) changes.temperature = inputs.temperature.value;
    return changes;
  }

  function submitProfile(person, inputs, formError, saveButton) {
    formError.textContent = "";
    Object.keys(FIELD_LABEL).forEach(function (key) { fieldError(key, ""); });

    var changes = changedFields(person, inputs);
    if (!Object.keys(changes).length) { state.editing = false; render(); return; }

    var blank = Object.keys(changes).filter(function (key) { return key !== "temperature" && changes[key] === ""; });
    if (blank.length) {
      blank.forEach(function (key) { fieldError(key, "Can't be empty. Leave it unchanged to keep the old value."); });
      $("f-" + blank[0]).focus();
      return;
    }
    var latest = state.data.calls[0];
    if (!latest) { formError.textContent = "There's no call to attach this change to."; return; }

    saveButton.disabled = true;
    saveButton.textContent = "Saving...";
    request("PATCH", "/api/calls/" + latest.id, changes).then(function () {
      toast("Saved. The change is logged and queued for Zoho.", null);
      return load();
    }).catch(function (error) {
      saveButton.disabled = false;
      saveButton.textContent = "Save changes";
      showSaveError(error, formError);
    });
  }

  function showSaveError(error, formError) {
    if (error.status === 409 && error.detail && error.detail.existing_applicant) {
      fieldError("phone", "That number already belongs to " + (error.detail.existing_applicant.name || "another applicant") + ".");
      $("f-phone").focus();
      return;
    }
    if (error.status === 422 && Array.isArray(error.detail) && error.detail[0] && error.detail[0].loc) {
      var key = error.detail[0].loc[error.detail[0].loc.length - 1];
      var messages = { phone: "Enter a US phone number with 10 digits.", state: "Use the two-letter state code, like TX." };
      if ($("f-" + key + "-error")) {
        fieldError(key, messages[key] || "Check this field.");
        $("f-" + key).focus();
        return;
      }
    }
    formError.textContent = "Couldn't save. Nothing was changed.";
  }

  function profileSection(person) {
    var edit = el("button", { cls: "btn btn-sm", text: "Edit", attrs: { type: "button" } });
    edit.addEventListener("click", function () { state.editing = true; render(); var first = $("f-name"); if (first) first.focus(); });
    var head = el("div", { cls: "side-head" }, el("h2", { text: "Profile" }));
    if (!state.editing) head.appendChild(edit);
    return el("section", { cls: "side-section" }, head, state.editing ? profileForm(person) : profileView(person));
  }

  // ---- follow-up note ---------------------------------------------------------------------

  function noteSection(person) {
    var area = el("textarea", { cls: "textarea", attrs: { id: "note", maxlength: "500", "aria-label": "Follow-up note", placeholder: "Best time to call, what they asked for, anything the next recruiter should know." } });
    area.value = person.follow_up.note || "";
    var status = el("span", { cls: "faint", text: person.follow_up.note ? "Saved" : "" });
    var save = el("button", { cls: "btn btn-sm", text: "Save note", attrs: { type: "button" } });
    area.addEventListener("input", function () { status.textContent = "Unsaved changes"; });
    save.addEventListener("click", function () {
      if (area.value.trim() === (person.follow_up.note || "")) { status.textContent = "Nothing to save"; return; }
      save.disabled = true;
      request("PATCH", "/api/applicants/" + person.id + "/follow-up", { note: area.value }).then(function () {
        toast("Note saved.", null);
        return load();
      }).catch(function () {
        save.disabled = false;
        status.textContent = "Couldn't save. Try again.";
      });
    });
    return el("section", { cls: "side-section" },
      el("div", { cls: "side-head" }, el("h2", { text: "Follow-up note" })), area, el("div", { cls: "note-foot" }, status, save));
  }

  // ---- Zoho -------------------------------------------------------------------------------

  function zohoSection(person, calls) {
    var latest = calls[0];
    var statusText = "Not queued";
    if (latest && latest.sync) {
      if (latest.sync.status === "sent") statusText = "Latest call sent " + (latest.sync.sent_at ? agoText(latest.sync.sent_at) : "recently");
      else if (latest.sync.status === "pending") statusText = "Waiting to send, try " + (latest.sync.attempts + 1);
      else statusText = "Failed after " + latest.sync.attempts + (latest.sync.attempts === 1 ? " try" : " tries");
    }
    var box = el("div", { cls: "profile" },
      el("div", { cls: "pf" }, el("span", { cls: "k", text: "Status" }), el("span", { cls: "v", text: statusText })),
      el("div", { cls: "pf" }, el("span", { cls: "k", text: "Candidate" }),
        el("span", { cls: "v mono" + (person.zoho_candidate_id ? "" : " faint"), text: person.zoho_candidate_id || "Not created yet" })));
    return el("section", { cls: "side-section" }, el("div", { cls: "side-head" }, el("h2", { text: "Zoho" })), box);
  }

  // ---- change history ---------------------------------------------------------------------

  function describe(entry) {
    var changes = entry.changes || {};
    if (entry.action === "update_follow_up") {
      var parts = [];
      if (changes.follow_up_status) parts.push("marked as " + (STATUS_LABEL[changes.follow_up_status.to] || changes.follow_up_status.to));
      if (changes.follow_up_note) parts.push("updated the note");
      return parts.join(" and ") || "updated the follow-up";
    }
    if (entry.action === "correct_applicant") {
      return "changed " + Object.keys(changes).map(function (key) {
        var change = changes[key];
        var from = key === "phone" ? phoneText(change.from) : change.from;
        var to = key === "phone" ? phoneText(change.to) : change.to;
        return (FIELD_LABEL[key] || key) + " from " + (from || "empty") + " to " + (to || "empty");
      }).join(", ");
    }
    if (entry.action === "attach_applicant") return "attached a call to this applicant";
    return "made a change";
  }

  function historySection(history) {
    var body;
    if (!history.length) {
      body = el("p", { cls: "faint", text: "No changes yet. Edits and follow-up updates show up here." });
    } else {
      body = el("ul", { cls: "history" });
      history.forEach(function (entry) {
        body.appendChild(el("li", {},
          el("span", { cls: "who-did", text: entry.username }), document.createTextNode(" " + describe(entry)),
          el("span", { cls: "when-did", text: agoText(entry.created_at), attrs: { title: whenText(entry.created_at) } })));
      });
    }
    return el("section", { cls: "side-section" }, el("div", { cls: "side-head" }, el("h2", { text: "Change history" })), body);
  }

  // ---- follow-up status -------------------------------------------------------------------

  function setFollowUp(next, previous) {
    if (state.busy || next === previous) return;
    state.busy = true;
    var id = state.data.applicant.id;
    request("PATCH", "/api/applicants/" + id + "/follow-up", { status: next }).then(function () {
      toast("Marked as " + STATUS_LABEL[next] + ".", "Undo", function () {
        request("PATCH", "/api/applicants/" + id + "/follow-up", { status: previous }).then(load)
          .catch(function () { toast("Couldn't undo. Try again.", null); });
      });
      return load();
    }).catch(function () {
      toast("Couldn't save that. Nothing was changed.", null);
    }).then(function () { state.busy = false; });
  }

  // ---- render -----------------------------------------------------------------------------

  function render() {
    var data = state.data;
    var person = data.applicant;
    $("crumb-name").textContent = person.name || "No name given";
    document.title = (person.name || "Applicant") + " | Frontline CDL";

    var side = el("aside", {}, profileSection(person), noteSection(person), zohoSection(person, data.calls), historySection(data.history));
    $("content").replaceChildren(header(person), el("div", { cls: "detail-grid" }, callsSection(data.calls), side));
    $("content").setAttribute("aria-busy", "false");
  }

  Desk.initTopbar();
  if (!applicantId) { renderNotFound(); } else { load(); }
})();
