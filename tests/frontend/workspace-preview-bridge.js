(function () {
  "use strict";
  const requestedCount = Number(new URLSearchParams(window.location.search).get("count"));
  const includeReview = new URLSearchParams(window.location.search).get("review") === "1";
  const startupMode = new URLSearchParams(window.location.search).get("startup");
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
  const reviewJobs = includeReview ? [{
    id: "review-preview-1",
    name: "IMG_0525.JPG",
    risks: ["low_confidence", "touches_edge"],
    detection_count: 1
  }] : [];

  function dispatch(name, payload) {
    window.app.receiveBackendEvent({ name, payload });
  }

  const api = {
    async bootstrap() {
      if (startupMode === "failed") {
        throw new Error("无法读取本地运行环境");
      }
      return {
        version: "v0.2.0-rc.5 · 视觉预览",
        gpu: "NVIDIA GeForce RTX 4070",
        runtime: "轻量 ONNX Runtime · 本地离线处理",
        models_ready: startupMode !== "models",
        model_issue: startupMode === "models"
          ? "模型文件不完整，请重新安装完整版本。"
          : "",
        webview2_version: "138.0",
        preset: "balanced",
        history_counts: { completed: 2, review_required: 0 },
        recovered_jobs: 0,
        database_recovered: false,
        settings_recovered: false
      };
    },
    async frontend_ready() {
      if (startupMode === "models") return true;
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
      return reviewJobs;
    },
    async get_review_job(identifier) {
      const item = reviewJobs.find((value) => value.id === identifier);
      if (!item) throw new Error("复核照片不存在");
      return {
        ...item,
        image: "/__preview__/source.jpg",
        width: 1920,
        height: 1280,
        preview_width: 1600,
        preview_height: 1067,
        detections: [{
          x1: 590,
          y1: 895,
          x2: 760,
          y2: 955,
          confidence: .72
        }],
        commands: []
      };
    },
    async get_adjustment_job(identifier) {
      const item = jobs.find((value) => value.id === identifier) ||
        reviewJobs.find((value) => value.id === identifier);
      if (!item) throw new Error("照片不存在");
      return {
        ...item,
        entry_available: true,
        message: "",
        image: "/__preview__/source.jpg",
        width: 1920,
        height: 1280,
        preview_width: 1600,
        preview_height: 1067,
        revision: "base",
        has_result: Boolean(item.output_available),
        detections: [{
          id: "detection:0",
          points: [[590, 895], [762, 887], [770, 956], [584, 963]],
          confidence: .72
        }],
        commands: [],
        risks: item.risks || []
      };
    },
    async preview_adjustment(identifier) {
      dispatch("adjustment_preview_started", { job_id: identifier });
      window.setTimeout(() => {
        dispatch("adjustment_preview_ready", {
          job_id: identifier,
          preview_token: "preview-token",
          image: "/__preview__/result.jpg",
          width: 1920,
          height: 1280,
          preview_width: 1600,
          preview_height: 1067,
          elapsed: 2.43
        });
      }, 600);
      return { accepted: true, message: "" };
    },
    async save_adjustment(identifier) {
      dispatch("adjustment_save_started", { job_id: identifier });
      window.setTimeout(() => {
        dispatch("adjustment_saved", {
          job_id: identifier,
          status: "completed",
          output_name: "IMG_0523_clean_2.JPG",
          elapsed: 2.43
        });
        dispatch("history_changed", {});
      }, 250);
      return { accepted: true, message: "" };
    },
    async cancel_adjustment() {
      return { accepted: true, cancelled: true, message: "" };
    },
    async reprocess_review(identifier) {
      dispatch("review_started", { job_id: identifier });
      window.setTimeout(() => {
        dispatch("review_finished", {
          job_id: identifier,
          status: "completed",
          elapsed: 2.43
        });
      }, 700);
      return { accepted: true, message: "" };
    },
    async skip_review(identifier) {
      window.setTimeout(() => dispatch("review_skipped", { job_id: identifier }), 80);
      return true;
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
