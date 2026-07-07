/* Light/dark theme, shared across the editor and settings screens.
 *
 * Loaded synchronously in <head> so the theme is applied before first
 * paint (no light flash). First visit follows the OS preference; the
 * toggle then overrides it and persists to localStorage under a key both
 * screens read, so the choice stays in sync between them.
 */
(function () {
  "use strict";
  var KEY = "invoicer_theme";
  var root = document.documentElement;

  function stored() {
    try {
      var v = localStorage.getItem(KEY);
      return v === "dark" || v === "light" ? v : null;
    } catch (e) {
      return null;
    }
  }

  function preferred() {
    try {
      return window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light";
    } catch (e) {
      return "light";
    }
  }

  function apply(theme) {
    root.setAttribute("data-theme", theme);
    var pressed = String(theme === "dark");
    var btns = document.querySelectorAll("[data-theme-toggle]");
    for (var i = 0; i < btns.length; i++) {
      btns[i].setAttribute("aria-pressed", pressed);
    }
  }

  apply(stored() || preferred());

  window.toggleTheme = function () {
    var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    apply(next);
    try {
      localStorage.setItem(KEY, next);
    } catch (e) {
      /* private mode: honor the toggle for this session only */
    }
  };
})();
