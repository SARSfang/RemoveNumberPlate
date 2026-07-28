(function () {
  "use strict";
  const PlateApp = window.PlateApp = window.PlateApp || {};
  const $ = (selector) => document.querySelector(selector);

  async function savePreset(event) {
    const select = event.currentTarget;
    const response = await PlateApp.bridge.call("set_preset", select.value);
    PlateApp.toast.show(response.message);
    if (!response.accepted) {
      const bootstrap = await PlateApp.bridge.call("bootstrap");
      select.value = bootstrap.preset || "balanced";
    }
  }

  function hydrate(bootstrap) {
    $("#gpu-name").textContent = bootstrap.gpu;
    $("#runtime-name").textContent = bootstrap.runtime;
    $("#model-state").textContent = bootstrap.models_ready
      ? "已校验，可以处理"
      : "模型缺失或校验失败";
    $("#model-state").style.color = bootstrap.models_ready
      ? "var(--success)"
      : "var(--danger)";
    $("#model-state").title = bootstrap.model_issue || "";
    $("#webview2-version").textContent = bootstrap.webview2_version;
    $("#preset").value = bootstrap.preset || "balanced";
  }

  function init() {
    $("#preset").addEventListener("change", savePreset);
    $("#export-diagnostics-button").addEventListener("click", async () => {
      const response = await PlateApp.bridge.call("export_diagnostics");
      if (response.message) PlateApp.toast.show(response.message);
    });
    document.querySelectorAll(".support-document").forEach((button) => {
      button.addEventListener("click", async () => {
        const opened = await PlateApp.bridge.call(
          "open_support_document",
          button.dataset.document
        );
        if (!opened) PlateApp.toast.show("帮助文档缺失，请重新安装应用。");
      });
    });
  }

  PlateApp.settings = { hydrate, init };
})();
