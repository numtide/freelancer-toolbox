// Modals loaded into #modal-root (send invoice, generated PDF, …): close on
// backdrop / × / Cancel / Escape, and focus the recipient field on load.
// Shared by the editor and the Invoices page.
(function () {
  function closeModal() {
    var root = document.getElementById("modal-root");
    if (root) root.innerHTML = "";
  }
  document.addEventListener("click", function (e) {
    var closer = e.target.closest("[data-modal-close]");
    if (!closer) return;
    // The overlay only closes on a direct backdrop click, not on clicks
    // that bubbled up from inside the card.
    if (closer.classList.contains("modal-overlay") && e.target !== closer) return;
    closeModal();
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && document.querySelector(".modal-overlay")) closeModal();
  });
  // Focus the first field when the modal loads.
  document.body.addEventListener("htmx:afterSwap", function (evt) {
    if (evt.target && evt.target.id === "modal-root") {
      var f = evt.target.querySelector('input[name="to"]');
      if (f) f.focus();
    }
  });
})();
