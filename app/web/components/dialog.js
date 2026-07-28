(function () {
  "use strict";
  const PlateApp = window.PlateApp = window.PlateApp || {};
  const focusableSelector = [
    "button:not(:disabled)",
    "[href]",
    "input:not(:disabled)",
    "select:not(:disabled)",
    "[tabindex]:not([tabindex='-1'])"
  ].join(",");
  let restoreFocus = null;
  let resolver = null;

  function elements() {
    return {
      backdrop: document.querySelector("#confirm-dialog"),
      title: document.querySelector("#dialog-title"),
      description: document.querySelector("#dialog-description"),
      cancel: document.querySelector("#dialog-cancel"),
      confirm: document.querySelector("#dialog-confirm")
    };
  }

  function close(accepted) {
    const { backdrop } = elements();
    if (!backdrop || backdrop.hidden) return;
    backdrop.hidden = true;
    const complete = resolver;
    resolver = null;
    if (restoreFocus && document.contains(restoreFocus)) restoreFocus.focus();
    restoreFocus = null;
    if (complete) complete(Boolean(accepted));
  }

  function confirm(options) {
    const parts = elements();
    if (!parts.backdrop) return Promise.resolve(false);
    restoreFocus = document.activeElement;
    parts.title.textContent = options.title || "确认操作";
    parts.description.textContent = options.description || "";
    parts.confirm.textContent = options.confirmLabel || "确认";
    parts.backdrop.hidden = false;
    window.setTimeout(() => parts.cancel.focus(), 0);
    return new Promise((resolve) => {
      resolver = resolve;
    });
  }

  function init() {
    const { backdrop, cancel, confirm: confirmButton } = elements();
    if (!backdrop) return;
    cancel.addEventListener("click", () => close(false));
    confirmButton.addEventListener("click", () => close(true));
    backdrop.addEventListener("mousedown", (event) => {
      if (event.target === backdrop) close(false);
    });
    backdrop.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        close(false);
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = [...backdrop.querySelectorAll(focusableSelector)];
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });
  }

  PlateApp.dialog = { close, confirm, init };
})();
