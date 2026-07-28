(function () {
  "use strict";
  const PlateApp = window.PlateApp = window.PlateApp || {};
  const $ = (selector) => document.querySelector(selector);

  async function savePreset(event) {
    const select = event.currentTarget;
    const previous = select.dataset.savedValue || "balanced";
    select.disabled = true;
    try {
      const response = await PlateApp.bridge.call("set_preset", select.value);
      PlateApp.toast.show(response.message);
      if (response.accepted) {
        select.dataset.savedValue = select.value;
      } else {
        select.value = previous;
      }
    } catch (error) {
      select.value = previous;
      PlateApp.toast.show(`无法保存处理预设：${error.message || error}`);
    } finally {
      select.disabled = false;
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
    $("#preset").dataset.savedValue = $("#preset").value;
  }

  function init() {
    $("#preset").addEventListener("change", savePreset);
    $("#export-diagnostics-button").addEventListener("click", async () => {
      const button = $("#export-diagnostics-button");
      button.disabled = true;
      try {
        const response = await PlateApp.bridge.call("export_diagnostics");
        if (response.message) PlateApp.toast.show(response.message);
      } catch (error) {
        PlateApp.toast.show(`无法导出诊断包：${error.message || error}`);
      } finally {
        button.disabled = false;
      }
    });
    document.querySelectorAll(".support-document").forEach((button) => {
      button.addEventListener("click", async () => {
        button.disabled = true;
        try {
          const opened = await PlateApp.bridge.call(
            "open_support_document",
            button.dataset.document
          );
          if (!opened) PlateApp.toast.show("帮助文档缺失，请重新安装应用。");
        } catch (error) {
          PlateApp.toast.show(`无法打开帮助文档：${error.message || error}`);
        } finally {
          button.disabled = false;
        }
      });
    });
  }

  PlateApp.settings = { hydrate, init };
})();
