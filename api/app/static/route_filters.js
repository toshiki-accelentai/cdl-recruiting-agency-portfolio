/* Reads the filters out of the page address, for example #applicants?status=to_call&readiness=hot.
   Only known filters with known values get through, so a hand-edited or hostile link can never put anything else
   into the page. Pure function: it is also run offline by tests/js/test_route_filters.js. */
(function (root) {
  "use strict";

  var ROUTES = ["overview", "applicants", "activity", "analytics"];
  var FOLLOW_UP = ["to_call", "called", "no_answer", "done"];
  var ALLOWED = {
    applicants: { status: ["all", "needs_contact"].concat(FOLLOW_UP), readiness: ["hot", "medium", "warm", "cold"] },
    activity: { sync: ["pending", "sent", "failed"], review: ["true", "false", "hang_up"], follow_up: FOLLOW_UP, day: ["today"] }
  };

  function has(object, key) { return Object.prototype.hasOwnProperty.call(object, key); }

  function parse(hash) {
    var body = (typeof hash === "string" ? hash : "").replace(/^#\/?/, "");
    var cut = body.indexOf("?");
    var name = cut < 0 ? body : body.slice(0, cut);
    var query = cut < 0 ? "" : body.slice(cut + 1);
    var route = ROUTES.indexOf(name) >= 0 ? name : "overview";
    var params = {};
    if (route !== name) return { route: route, params: params };
    var allowed = has(ALLOWED, route) ? ALLOWED[route] : {};
    query.split("&").forEach(function (pair) {
      if (!pair) return;
      var eq = pair.indexOf("=");
      var key = eq < 0 ? pair : pair.slice(0, eq);
      var value = eq < 0 ? "" : pair.slice(eq + 1);
      try {
        key = decodeURIComponent(key);
        value = decodeURIComponent(value);
      } catch (error) { return; }
      if (!has(allowed, key) || has(params, key) || allowed[key].indexOf(value) < 0) return;
      params[key] = value;
    });
    return { route: route, params: params };
  }

  var api = { parse: parse };
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.routeFilters = api;
})(typeof window !== "undefined" ? window : globalThis);
