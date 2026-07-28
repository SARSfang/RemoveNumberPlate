(function () {
  "use strict";
  const requestedCount = Number(new URLSearchParams(window.location.search).get("count"));
  const jobCount = Math.max(1, Math.min(500, requestedCount || 10));
  const jobs = Array.from({ length: jobCount }, (_, index) => ({
    id: `preview-${index + 1}`,
    name: `IMG_${String(523 + index).padStart(4, "0")}.JPG`,
    status: index < 2 ? "completed" : index < 4 ? "detecting" : "queued",
    index: index + 1,
    elapsed: index < 2 ? 3.2 + index * .4 : null,
    detection_count: index < 2 ? 1 : 0,
    risks: [],
    output_available: index < 2
  }));

  function dispatch(name, payload) {
    window.app.receiveBackendEvent({ name, payload });
  }

  const api = {
    async bootstrap() {
      return {
        version: "v0.2.0-rc.5 · 视觉预览",
        gpu: "NVIDIA GeForce RTX 4070",
        runtime: "轻量 ONNX Runtime · 本地离线处理",
        models_ready: true,
        model_issue: "",
        webview2_version: "138.0",
        preset: "balanced",
        history_counts: { completed: 2, review_required: 0 },
        recovered_jobs: 0,
        database_recovered: false,
        settings_recovered: false
      };
    },
    async frontend_ready() {
      window.setTimeout(() => {
        dispatch("batch_accepted", {});
        dispatch("batch_discovered", { total: jobs.length });
        dispatch("batch_items_ready", {
          items: jobs.map((job) => ({
            job_id: job.id,
            name: job.name,
            index: job.index,
            status: "queued"
          }))
        });
        jobs.slice(0, 2).forEach((job) => {
          dispatch("item_started", {
            job_id: job.id,
            name: job.name,
            index: job.index,
            total: jobs.length
          });
          dispatch("item_finished", {
            job_id: job.id,
            name: job.name,
            index: job.index,
            total: jobs.length,
            status: "completed",
            elapsed: job.elapsed,
            output_available: true,
            detection_count: 1,
            risks: [],
            error: ""
          });
        });
        dispatch("item_started", {
          job_id: jobs[2].id,
          name: jobs[2].name,
          index: 3,
          total: jobs.length
        });
      }, 40);
      return true;
    },
    async list_review_jobs() {
      return [];
    },
    async list_history() {
      return jobs.slice(0, 2).map((job) => ({
        ...job,
        updated_at: new Date().toISOString(),
        source_available: true,
        error: ""
      }));
    },
    async get_job_preview(_identifier, variant) {
      return {
        available: true,
        image: variant === "result"
          ? "/__preview__/result.jpg"
          : "/__preview__/source.jpg",
        width: 1920,
        height: 1280,
        preview_width: 1600,
        preview_height: 1067,
        variant,
        reason: "",
        message: ""
      };
    },
    async get_job_thumbnail(identifier) {
      const job = jobs.find((item) => item.id === identifier);
      return {
        available: true,
        image: job && job.output_available
          ? "/__preview__/result.jpg"
          : "/__preview__/source.jpg",
        width: 1920,
        height: 1280,
        preview_width: 320,
        preview_height: 213,
        variant: job && job.output_available ? "result" : "original",
        reason: "",
        message: ""
      };
    },
    async open_job_output() {
      return true;
    },
    async choose_files() {
      return [];
    },
    async choose_folder() {
      return [];
    },
    async set_preset() {
      return { accepted: true, message: "处理预设已保存。" };
    },
    async export_diagnostics() {
      return { accepted: true, message: "视觉预览不导出诊断包。" };
    },
    async open_support_document() {
      return true;
    },
    async pause() {
      dispatch("paused", { paused: true });
      return true;
    },
    async resume() {
      dispatch("paused", { paused: false });
      return true;
    },
    async cancel() {
      return true;
    }
  };

  window.pywebview = { api };
})();
