/* Transient toasts, driven by the server via htmx.
 *
 * Handlers that commit an action (sync, generate PDF, send invoice, save
 * settings) return an `HX-Trigger: {"showtoast": {title, body, kind}}`
 * response header. htmx turns that into a `showtoast` DOM event; we render
 * a bottom-center card with a status badge, a bold title, and an optional
 * muted body line, that slides up and auto-dismisses.
 */
(function () {
  "use strict";

  var CHECK =
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" ' +
    'stroke="#fff" stroke-width="3"><path d="M20 6 9 17l-5-5"></path></svg>';
  var CROSS =
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" ' +
    'stroke="#fff" stroke-width="3"><path d="M18 6 6 18M6 6l12 12"></path></svg>';

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

  function show(title, body, kind) {
    if (!title && !body) return;
    var isErr = kind === "err";
    var el = document.createElement("div");
    el.className = "toast" + (isErr ? " toast-err" : "");
    el.setAttribute("role", isErr ? "alert" : "status");

    var badge = document.createElement("span");
    badge.className = "toast-badge";
    badge.innerHTML = isErr ? CROSS : CHECK;

    var text = document.createElement("div");
    text.className = "toast-text";
    var t = document.createElement("div");
    t.className = "toast-title";
    t.textContent = title || "";
    text.appendChild(t);
    if (body) {
      var b = document.createElement("div");
      b.className = "toast-body hv-num";
      b.textContent = body;
      text.appendChild(b);
    }

    el.appendChild(badge);
    el.appendChild(text);

    function dismiss() {
      clearTimeout(timer);
      el.classList.remove("in");
      setTimeout(function () {
        el.remove();
      }, 260);
    }

    el.addEventListener("click", dismiss);
    container().appendChild(el);
    requestAnimationFrame(function () {
      el.classList.add("in");
    });
    // Errors linger longer so they can be read before they vanish.
    var timer = setTimeout(dismiss, isErr ? 6000 : 3800);
  }

  window.showToast = show;

  document.addEventListener("DOMContentLoaded", function () {
    document.body.addEventListener("showtoast", function (evt) {
      var d = evt.detail || {};
      show(d.title || "", d.body || "", d.kind || "ok");
    });
  });
})();
