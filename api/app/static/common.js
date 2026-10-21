/* Shared by the recruiter pages: a text-only DOM builder, formatting, toast, sign-out. */
(function () {
  "use strict";

  var TZ = "America/Vancouver"; // the agency's business time zone
  var TOAST_MS = 7000;

  function $(id) { return document.getElementById(id); }

  // Text only, never HTML: names, notes and errors come from callers.
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

  function toLogin() { window.location.assign("/login"); }

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

  var HEAT = {
    HOT: { label: "Hot", bars: 4, chip: "chip-hot" },
    MEDIUM: { label: "Medium", bars: 3, chip: "chip-medium" },
    WARM: { label: "Warm", bars: 2, chip: "chip-warm" },
    COLD: { label: "Cold", bars: 1, chip: "chip-cold" },
  };
  var FOLLOW_UP = {
    to_call: { label: "To contact", cls: "status-to-call", symbol: "○" },
    called: { label: "Called", cls: "status-called", symbol: "↗" },
    no_answer: { label: "No answer", cls: "status-no-answer", symbol: "↻" },
    done: { label: "Done", cls: "status-done", symbol: "✓" }
  };

  // Four bars plus a word, so urgency never depends on color alone.
  function heatChip(temperature) {
    var spec = Object.prototype.hasOwnProperty.call(HEAT, temperature) ? HEAT[temperature] : { label: "Not set", bars: 0, chip: "chip-calm" };
    var bars = el("span", { cls: "heat", attrs: { "aria-hidden": "true" } });
    for (var i = 1; i <= 4; i++) bars.appendChild(el("i", { cls: i <= spec.bars ? "on" : "" }));
    return el("span", { cls: "chip " + spec.chip }, bars, el("span", { text: spec.label }));
  }

  function followUpChip(status) {
    var spec = Object.prototype.hasOwnProperty.call(FOLLOW_UP, status) ? FOLLOW_UP[status] : { label: "Not set", cls: "", symbol: "·" };
    return el("span", { cls: "status-chip " + spec.cls },
      el("span", { cls: "status-symbol", text: spec.symbol, attrs: { "aria-hidden": "true" } }), el("span", { text: spec.label }));
  }

  function phoneLink(e164, extraCls) {
    return el("a", { cls: "phone mono" + (extraCls ? " " + extraCls : ""), text: phoneText(e164), attrs: { href: "tel:" + e164 } });
  }

  // Top bar: who is signed in, and sign out.
  function initTopbar() {
    $("signout").addEventListener("click", function () {
      fetch("/logout", { method: "POST" }).then(toLogin, toLogin);
    });
    fetch("/api/me").then(function (r) { return r.ok ? r.json() : null; }).then(function (me) {
      if (me) $("who").textContent = me.username;
    }).catch(function () {});
  }

  window.Desk = {
    TZ: TZ, $: $, el: el, phoneText: phoneText, timeText: timeText, whenText: whenText, agoText: agoText,
    clip: clip, toLogin: toLogin, toast: toast, heatChip: heatChip, followUpChip: followUpChip, phoneLink: phoneLink, initTopbar: initTopbar,
  };
})();
