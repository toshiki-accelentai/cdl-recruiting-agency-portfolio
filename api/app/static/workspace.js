(function () {
  "use strict";

  var Desk = window.Desk;
  var labels = { overview: "Overview", applicants: "Applicants", activity: "Call activity", analytics: "Analytics" };

  function currentRoute() {
    if (/^\/applicants\/\d+/.test(window.location.pathname)) return "applicants";
    var route = window.location.hash.replace(/^#\/?/, "").split("?")[0];
    return Object.prototype.hasOwnProperty.call(labels, route) ? route : "overview";
  }

  function update() {
    var route = currentRoute();
    Desk.currentRoute = route;
    document.querySelectorAll("[data-route]").forEach(function (link) {
      var active = link.getAttribute("data-route") === route;
      if (active) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
    var context = Desk.$("workspace-context");
    if (context) context.textContent = labels[route];
    var views = document.querySelectorAll("[data-view]");
    if (views.length) {
      views.forEach(function (view) { view.hidden = view.getAttribute("data-view") !== route; });
      document.title = labels[route] + " | Frontline CDL";
      // The filters carried by the address, for example #applicants?status=to_call (empty when the link has none).
      var parsed = window.routeFilters ? window.routeFilters.parse(window.location.hash) : { route: route, params: {} };
      window.dispatchEvent(new CustomEvent("desk:route", { detail: { route: route, params: parsed.route === route ? parsed.params : {} } }));
    }
  }

  window.addEventListener("hashchange", update);
  update();
  Desk.initTopbar();
})();
