(function () {
  "use strict";
  const PlateApp = window.PlateApp = window.PlateApp || {};
  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => [...document.querySelectorAll(selector)];

  PlateApp.store = PlateApp.state.createStore();

  function navigate(name) {
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
    if (name === "review") PlateApp.review.refresh();
    if (name === "history") PlateApp.history.refresh();
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
      button.addEventListener("click", () => navigate(button.dataset.page));
    });
    $$("[data-go-page]").forEach((button) => {
      button.addEventListener("click", () => navigate(button.dataset.goPage));
    });
  }

  async function hydrate() {
    try {
      const bootstrap = await PlateApp.bridge.call("bootstrap");
      PlateApp.store.patch({
        bootstrap,
        modelsReady: Boolean(bootstrap.models_ready)
      }, "bootstrap_ready");
      $("#app-version").textContent = bootstrap.version;
      $("#choose-files").disabled = !bootstrap.models_ready;
      $("#choose-folder").disabled = !bootstrap.models_ready;
      $("#drop-zone").classList.toggle("is-disabled", !bootstrap.models_ready);
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
      PlateApp.toast.show(`界面初始化失败：${error.message || error}`);
    }
  }

  initializeUi();
  PlateApp.bridge.ready(hydrate);
})();
