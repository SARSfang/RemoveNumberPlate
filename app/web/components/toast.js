(function () {
  "use strict";
  const PlateApp = window.PlateApp = window.PlateApp || {};
  let timer = null;

  function show(message, duration) {
    const toast = document.querySelector("#toast");
    if (!toast || !message) return;
    toast.textContent = String(message);
    toast.hidden = false;
    window.clearTimeout(timer);
    timer = window.setTimeout(() => {
      toast.hidden = true;
    }, Number(duration || 4200));
  }

  PlateApp.toast = { show };
})();
