/* Transient toasts, driven by the server via htmx.
 *
 * Handlers that commit an action (generate PDF, send invoice, save
 * settings) return an `HX-Trigger: {"showtoast": {...}}` response header.
 * htmx turns that into a `showtoast` DOM event; we render a small
 * auto-dismissing card, bottom-right, in the success or error style.
 * The inline status text next to each control stays as a persistent
 * record — the toast is the glanceable confirmation.
 */
(function () {
  "use strict";

  function container() {
    var c = document.getElementById("toasts");
    if (!c) {
      c = document.createElement("div");
      c.id = "toasts";
      c.setAttribute("aria-live", "polite");
      document.body.appendChild(c);
    }
    return c;
  }

  function show(message, kind) {
    if (!message) return;
    var isErr = kind === "err";
    var el = document.createElement("div");
    el.className = "toast" + (isErr ? " toast-err" : "");
    el.setAttribute("role", isErr ? "alert" : "status");
    el.textContent = message;

    function dismiss() {
      clearTimeout(timer);
      el.classList.remove("in");
      setTimeout(function () {
        el.remove();
      }, 220);
    }

    el.addEventListener("click", dismiss);
    container().appendChild(el);
    requestAnimationFrame(function () {
      el.classList.add("in");
    });
    // Errors linger longer so they can be read before they vanish.
    var timer = setTimeout(dismiss, isErr ? 6000 : 3500);
  }

  window.showToast = show;

  document.addEventListener("DOMContentLoaded", function () {
    document.body.addEventListener("showtoast", function (evt) {
      var d = evt.detail || {};
      show(d.message || "", d.kind || "ok");
    });
  });
})();
