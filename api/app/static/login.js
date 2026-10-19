(function () {
  "use strict";

  var form = document.getElementById("login-form");
  var username = document.getElementById("username");
  var password = document.getElementById("password");
  var errorBox = document.getElementById("form-error");
  var submit = document.getElementById("submit");
  var reveal = document.getElementById("reveal");

  function showError(message, field) {
    errorBox.textContent = message;
    username.removeAttribute("aria-invalid");
    password.removeAttribute("aria-invalid");
    if (field) {
      field.setAttribute("aria-invalid", "true");
      field.focus();
    }
  }

  reveal.addEventListener("click", function () {
    var showing = password.type === "text";
    password.type = showing ? "password" : "text";
    reveal.textContent = showing ? "Show" : "Hide";
    reveal.setAttribute("aria-pressed", String(!showing));
  });

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    showError("");
    if (!username.value.trim()) { showError("Enter your username.", username); return; }
    if (!password.value) { showError("Enter your password.", password); return; }

    submit.disabled = true;
    submit.textContent = "Signing in...";

    fetch("/login", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ username: username.value.trim(), password: password.value }),
    }).then(function (response) {
      if (response.ok) { window.location.assign("/"); return; }
      submit.disabled = false;
      submit.textContent = "Sign in";
      if (response.status === 401) {
        showError("That username or password isn't right. Try again.", password);
        password.select();
      } else if (response.status === 429) {
        var minutes = Math.max(1, Math.ceil(Number(response.headers.get("Retry-After")) / 60));
        showError("Too many tries. Wait about " + minutes + (minutes === 1 ? " minute" : " minutes") + " and try again.");
      } else {
        showError("Sign in isn't available right now. Try again in a minute.");
      }
    }).catch(function () {
      submit.disabled = false;
      submit.textContent = "Sign in";
      showError("Couldn't reach the server. Check your connection and try again.");
    });
  });
})();
