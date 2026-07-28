(function () {
  "use strict";
  const PlateApp = window.PlateApp = window.PlateApp || {};
  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => [...document.querySelectorAll(selector)];
  let currentPage = "batch";
  let hydrationSerial = 0;

  PlateApp.store = PlateApp.state.createStore();

  async function navigate(name) {
    if (
      currentPage === "review" &&
      name !== "review" &&
      PlateApp.review.state.dirty
    ) {
      if (!await PlateApp.review.confirmDiscard()) return false;
      PlateApp.review.discardEdits();
    }
    $$(".nav-item").forEach((button) => {
      const active = button.dataset.page === name;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-current", active ? "page" : "false");
    });
    $$(".page").forEach((page) => {
      page.classList.toggle("is-active", page.id === `page-${name}`);
    });
    const heading = $(`#page-${name} h1`);
    if (heading) heading.focus({ preventScroll: true });
    if (name === "review") {
      PlateApp.review.refresh();
      PlateApp.review.activate();
    }
    if (name === "history") PlateApp.history.refresh();
    currentPage = name;
    return true;
  }

  PlateApp.navigate = navigate;

  function patchReviewedJob(identifier, patch) {
    const current = PlateApp.store.get();
    const jobs = current.jobs.map((job) =>
      job.job_id === identifier ? { ...job, ...patch } : job
    );
    PlateApp.store.patch({ jobs }, "review_job_updated");
    PlateApp.preview.invalidate(identifier);
    PlateApp.filmstrip.invalidate(identifier);
    PlateApp.filmstrip.render();
    if (current.selectedId === identifier) {
      PlateApp.preview.show(jobs.find((job) => job.job_id === identifier));
    }
  }

  function receiveBackendEvent(event) {
    PlateApp.batch.receiveBackendEvent(event);
    PlateApp.review.handleEvent(event);
    if (event.name === "review_finished") {
      patchReviewedJob(event.payload.job_id, {
        status: "completed",
        output_available: true,
        elapsed: Number(event.payload.elapsed || 0)
      });
    } else if (event.name === "review_skipped") {
      patchReviewedJob(event.payload.job_id, { status: "cancelled" });
    } else if (event.name === "history_changed") {
      PlateApp.history.refresh();
    }
  }

  window.app = { receiveBackendEvent };

  function initializeUi() {
    PlateApp.dialog.init();
    PlateApp.preview.init();
    PlateApp.filmstrip.init();
    PlateApp.batch.init();
    PlateApp.review.init();
    PlateApp.history.init();
    PlateApp.settings.init();
    PlateApp.shortcuts.init();
    PlateApp.batch.renderState();

    $$(".nav-item").forEach((button) => {
      button.addEventListener("click", async () => {
        await navigate(button.dataset.page);
      });
    });
    $$("[data-go-page]").forEach((button) => {
      button.addEventListener("click", async () => {
        await navigate(button.dataset.goPage);
      });
    });
    $("#startup-retry-button").addEventListener("click", hydrate);
  }

  function setStartupState(kind, detail) {
    const retryButton = $("#startup-retry-button");
    const ready = kind === "ready";
    const loading = kind === "loading";
    $("#choose-files").hidden = !ready;
    $("#choose-folder").hidden = !ready;
    $("#choose-files").disabled = !ready;
    $("#choose-folder").disabled = !ready;
    retryButton.hidden = ready || loading;
    retryButton.disabled = loading;
    $("#drop-zone").classList.toggle("is-disabled", loading);

    if (loading) {
      $("#drop-eyebrow").textContent = "正在检查本地组件";
      $("#drop-title").textContent = "正在准备 AI 引擎";
      $("#drop-lead").textContent = "首次启动可能需要几秒钟。";
    } else if (kind === "models_missing") {
      $("#drop-eyebrow").textContent = "需要修复安装";
      $("#drop-title").textContent = "AI 模型未就绪";
      $("#drop-lead").textContent = detail || "请重新安装完整版本后再次检测。";
    } else if (kind === "failed") {
      $("#drop-eyebrow").textContent = "启动未完成";
      $("#drop-title").textContent = "应用未能完成启动";
      $("#drop-lead").textContent = detail || "请重新检测；如果仍失败，可在设置中打开诊断文件夹。";
    } else {
      $("#drop-eyebrow").textContent = "本地批量处理";
      $("#drop-title").textContent = "把整组照片拖到这里";
      $("#drop-lead").textContent = "自动检测并消除车牌，原片永不覆盖。";
    }
  }

  async function hydrate() {
    const serial = ++hydrationSerial;
    setStartupState("loading");
    $("#app-version").textContent = "正在启动…";
    try {
      const bootstrap = await PlateApp.bridge.call("bootstrap");
      if (serial !== hydrationSerial) return;
      PlateApp.store.patch({
        bootstrap,
        modelsReady: Boolean(bootstrap.models_ready)
      }, "bootstrap_ready");
      $("#app-version").textContent = bootstrap.version;
      setStartupState(
        bootstrap.models_ready ? "ready" : "models_missing",
        bootstrap.model_issue
      );
      PlateApp.settings.hydrate(bootstrap);
      await Promise.all([
        PlateApp.review.refresh(),
        PlateApp.history.refresh()
      ]);
      const recoveryMessages = [];
      if (bootstrap.database_recovered) {
        recoveryMessages.push("任务历史数据库损坏，已保留原文件并创建新的安全数据库。");
      }
      if (bootstrap.settings_recovered) {
        recoveryMessages.push("设置文件无效，已保留原文件并恢复默认设置。");
      }
      if (bootstrap.recovered_jobs > 0) {
        recoveryMessages.push(
          `发现 ${bootstrap.recovered_jobs} 个中断任务，可在任务历史中重新处理。`
        );
      }
      if (recoveryMessages.length) PlateApp.toast.show(recoveryMessages.join(" "));
      await PlateApp.bridge.call("frontend_ready");
    } catch (error) {
      if (serial !== hydrationSerial) return;
      const message = error.message || String(error);
      $("#app-version").textContent = "启动失败";
      setStartupState("failed", message);
      PlateApp.toast.show(`界面初始化失败：${message}`);
    }
  }

  initializeUi();
  PlateApp.bridge.ready(hydrate);
})();
