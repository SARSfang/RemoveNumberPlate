(function () {
  "use strict";
  const PlateApp = window.PlateApp = window.PlateApp || {};

  function api() {
    return window.pywebview && window.pywebview.api
      ? window.pywebview.api
      : null;
  }

  async function call(method, ...args) {
    const target = api();
    if (!target || typeof target[method] !== "function") {
      throw new Error(`桌面桥接尚未就绪：${method}`);
    }
    return target[method](...args);
  }

  function ready(callback) {
    if (api()) {
      callback();
      return;
    }
    window.addEventListener("pywebviewready", callback, { once: true });
  }

  PlateApp.bridge = { api, call, ready };
})();
