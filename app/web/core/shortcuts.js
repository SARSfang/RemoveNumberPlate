(function () {
  "use strict";
  const PlateApp = window.PlateApp = window.PlateApp || {};
  const $ = (selector) => document.querySelector(selector);

  function activePage() {
    const page = document.querySelector(".page.is-active");
    return page ? page.id.replace("page-", "") : "";
  }

  function isTypingTarget(target) {
    return Boolean(
      target &&
      (
        ["INPUT", "SELECT", "TEXTAREA"].includes(target.tagName) ||
        target.isContentEditable
      )
    );
  }

  function dialogOpen() {
    const dialog = $("#confirm-dialog");
    return dialog && !dialog.hidden;
  }

  function handleBatch(event) {
    if (!PlateApp.store.get().jobs.length) return;
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      PlateApp.filmstrip.move(-1);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      PlateApp.filmstrip.move(1);
    } else if (event.key === "Home") {
      event.preventDefault();
      PlateApp.filmstrip.edge("start");
    } else if (event.key === "End") {
      event.preventDefault();
      PlateApp.filmstrip.edge("end");
    } else if (event.key === "1") {
      event.preventDefault();
      $("#preview-tab-original").click();
    } else if (event.key === "2") {
      event.preventDefault();
      $("#preview-tab-result").click();
    } else if (event.key.toLowerCase() === "f") {
      event.preventDefault();
      PlateApp.batch.restoreFollowing();
    }
  }

  function handleReview(event) {
    const canvasFocused = document.activeElement === $("#review-canvas");
    if (event.code === "Space" && canvasFocused && !event.repeat) {
      event.preventDefault();
      PlateApp.review.state.spaceDown = true;
      $("#review-canvas").style.cursor = "grab";
      return;
    }
    if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === "z") {
      event.preventDefault();
      $("#redo-button").click();
    } else if (event.ctrlKey && event.key.toLowerCase() === "z") {
      event.preventDefault();
      $("#undo-button").click();
    } else if (event.ctrlKey && event.key.toLowerCase() === "y") {
      event.preventDefault();
      $("#redo-button").click();
    } else if (!event.ctrlKey && ["r", "b", "e"].includes(event.key.toLowerCase())) {
      const tool = {
        r: "rectangle",
        b: "brush_add",
        e: "brush_erase"
      }[event.key.toLowerCase()];
      const button = document.querySelector(`.tool-button[data-tool="${tool}"]`);
      if (button) {
        event.preventDefault();
        button.click();
      }
    } else if (!event.ctrlKey && event.key === "[") {
      event.preventDefault();
      PlateApp.review.move(-1);
    } else if (!event.ctrlKey && event.key === "]") {
      event.preventDefault();
      PlateApp.review.move(1);
    }
  }

  function init() {
    window.addEventListener("keydown", (event) => {
      if (dialogOpen() || isTypingTarget(event.target)) return;
      if (event.ctrlKey && event.key.toLowerCase() === "o") {
        event.preventDefault();
        PlateApp.batch.chooseFiles();
        return;
      }
      if (activePage() === "batch") handleBatch(event);
      if (activePage() === "review") handleReview(event);
    });
    window.addEventListener("keyup", (event) => {
      if (event.code !== "Space" || activePage() !== "review") return;
      PlateApp.review.state.spaceDown = false;
      $("#review-canvas").style.cursor =
        PlateApp.review.state.tool === "remove_detection"
          ? "not-allowed"
          : "crosshair";
    });
  }

  PlateApp.shortcuts = { init };
})();
