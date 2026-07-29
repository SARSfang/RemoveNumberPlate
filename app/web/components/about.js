(function () {
  "use strict";
  const PlateApp = window.PlateApp = window.PlateApp || {};
  const $ = (selector) => document.querySelector(selector);
  const focusableSelector = [
    "button:not(:disabled)",
    "[href]",
    "input:not(:disabled)",
    "select:not(:disabled)",
    "[tabindex]:not([tabindex='-1'])"
  ].join(",");
  let restoreFocus = null;

  function open() {
    const backdrop = $("#about-dialog");
    if (!backdrop || !backdrop.hidden) return;
    restoreFocus = document.activeElement;
    populate();
    backdrop.hidden = false;
    const okButton = $("#about-dialog-ok");
    const close = $("#about-dialog-close");
    window.setTimeout(() => {
      (okButton || close || backdrop).focus();
    }, 0);
  }

  function close() {
    const backdrop = $("#about-dialog");
    if (!backdrop || backdrop.hidden) return;
    backdrop.hidden = true;
    if (restoreFocus && document.contains(restoreFocus)) {
      restoreFocus.focus();
    }
    restoreFocus = null;
  }

  function populate() {
    const state = PlateApp.store && PlateApp.store.get ? PlateApp.store.get() : null;
    const bootstrap = (state && state.bootstrap) || {};
    const versionText = $("#about-version-text");
    const runtimeText = $("#about-runtime");
    const schemaText = $("#about-schema");
    if (versionText) {
      versionText.textContent = bootstrap.version || bootstrap.version_raw || "—";
    }
    if (runtimeText) {
      runtimeText.textContent = bootstrap.runtime || "—";
    }
    if (schemaText) {
      schemaText.textContent = bootstrap.schema_version != null
        ? `v${bootstrap.schema_version}`
        : "—";
    }
  }

  function init() {
    const backdrop = $("#about-dialog");
    if (!backdrop) return;
    const aboutButton = $("#about-button");
    if (aboutButton) {
      aboutButton.addEventListener("click", open);
    }
    const closeButton = $("#about-dialog-close");
    if (closeButton) {
      closeButton.addEventListener("click", close);
    }
    const okButton = $("#about-dialog-ok");
    if (okButton) {
      okButton.addEventListener("click", close);
    }
    backdrop.addEventListener("mousedown", (event) => {
      if (event.target === backdrop) close();
    });
    backdrop.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        close();
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

  PlateApp.about = { open, close, init };
})();
