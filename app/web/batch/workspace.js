(function () {
  "use strict";
  const PlateApp = window.PlateApp = window.PlateApp || {};
  const $ = (selector) => document.querySelector(selector);

  const STATUS_LABELS = {
    queued: "排队中",
    detecting: "检测中",
    auto_ready: "检测完成",
    review_required: "待复核",
    no_plate: "未发现车牌",
    inpainting: "修复中",
    writing: "写入中",
    completed: "已完成",
    failed: "失败",
    cancelled: "已取消"
  };

  const RISK_LABELS = {
    low_confidence: "低置信度",
    plate_too_small: "区域过小",
    touches_edge: "靠近边缘",
    abnormal_box: "比例异常",
    overlapping_boxes: "候选重叠",
    invalid_coordinates: "坐标异常",
    gpu_out_of_memory: "内存不足",
    inpaint_failed: "修复失败",
    write_failed: "写入失败"
  };
  let detailsRestoreFocus = null;

  function jobById(identifier) {
    return PlateApp.store.get().jobs.find((job) => job.job_id === identifier);
  }

  function outputName(name) {
    const dot = name.lastIndexOf(".");
    if (dot < 0) return `${name}_clean`;
    return `${name.slice(0, dot)}_clean${name.slice(dot)}`;
  }

  async function updateInspectorThumbnail(job) {
    const thumbnail = $("#inspector-thumbnail");
    thumbnail.style.backgroundImage = "";
    if (!job) return;
    const cached = PlateApp.filmstrip.thumbnailCache.get(job.job_id);
    if (cached) {
      thumbnail.style.backgroundImage = `url("${cached}")`;
      return;
    }
    try {
      const response = await PlateApp.bridge.call("get_job_thumbnail", job.job_id);
      if (
        response &&
        response.available &&
        PlateApp.store.get().selectedId === job.job_id
      ) {
        PlateApp.filmstrip.thumbnailCache.set(job.job_id, response.image);
        thumbnail.style.backgroundImage = `url("${response.image}")`;
      }
    } catch (_error) {
      // The details panel remains usable without a thumbnail.
    }
  }

  function setProgress(value) {
    const safe = Math.max(0, Math.min(100, Number(value || 0)));
    $("#progress-fill").style.width = `${safe}%`;
    $(".progress-track").setAttribute("aria-valuenow", String(Math.round(safe)));
    $("#progress-percent").textContent = `${Math.round(safe)}%`;
  }

  function updateInspector(job) {
    const status = $("#inspector-status");
    const statusCopy = $("#inspector-status-copy");
    if (!job) {
      updateInspectorThumbnail(null);
      $("#preview-file-name").textContent = "—";
      status.className = "status status-queued";
      status.textContent = "排队中";
      statusCopy.textContent = "等待处理";
      $("#inspector-elapsed").textContent = "—";
      $("#inspector-detections").textContent = "—";
      $("#inspector-risks").textContent = "—";
      $("#inspector-output-name").textContent = "结果尚未生成";
      $("#open-job-output-button").disabled = true;
      return;
    }
    updateInspectorThumbnail(job);
    $("#preview-file-name").textContent = job.name;
    $("#preview-file-name").title = job.name;
    status.className = `status status-${job.status}`;
    status.textContent = STATUS_LABELS[job.status] || job.status;
    statusCopy.textContent = STATUS_LABELS[job.status] || job.status;
    $("#inspector-status-icon").style.color = job.status === "completed"
      ? "var(--success)"
      : job.status === "failed"
        ? "var(--danger)"
        : job.status === "review_required"
          ? "var(--warning)"
          : "var(--accent-hover)";
    $("#inspector-elapsed").textContent = job.elapsed == null
      ? "—"
      : `${job.elapsed.toFixed(2)} 秒`;
    $("#inspector-detections").textContent = job.detection_count
      ? `${job.detection_count} 处`
      : job.status === "completed" ? "0 处" : "—";
    $("#inspector-risks").textContent = job.risks.length
      ? job.risks.map((risk) => RISK_LABELS[risk] || risk).join("、")
      : "无";
    $("#inspector-output-name").textContent = job.output_available
      ? outputName(job.name)
      : "结果尚未生成";
    $("#open-job-output-button").disabled = !job.output_available;
    $("#inspector-review-button").disabled = job.status !== "review_required";
    $("#inspector-retry-button").disabled = !["queued", "failed", "cancelled"].includes(job.status);
  }

  function updateFollowingState(state) {
    const following = state.previewMode === "following";
    const chip = $("#follow-state");
    chip.classList.toggle("is-following", following);
    chip.innerHTML = `<span class="status-dot"></span>${following ? "自动跟随" : "已固定"}`;
    $("#restore-follow-button").hidden = following;
    if (!state.processingId) {
      $("#processing-position").textContent = state.running ? "准备任务" : "批次已结束";
      return;
    }
    const current = jobById(state.processingId);
    $("#processing-position").textContent = current
      ? `处理中 ${current.index} / ${state.total}`
      : "处理中";
  }

  function renderState() {
    const state = PlateApp.store.get();
    const values = PlateApp.state.counts(state);
    const hasSession = state.running || state.jobs.length > 0;
    $("#batch-empty").hidden = hasSession;
    $("#batch-workspace").hidden = !hasSession;
    if (!hasSession) return;

    $("#batch-summary").textContent = `${state.total} 张照片`;
    $("#review-button-count").textContent = `(${values.review_required})`;
    $("#review-button").disabled = values.review_required === 0;
    $("#pause-button").disabled = !state.running;
    $("#cancel-button").disabled = !state.running;
    $("#add-files-button").disabled = state.running;
    $("#pause-button").lastChild.textContent = state.paused ? "继续" : "暂停";

    const progress = state.total ? values.finished / state.total * 100 : 0;
    setProgress(progress);
    $("#progress-count").textContent = `${values.finished} / ${state.total}`;

    const processing = state.processingId && jobById(state.processingId);
    if (state.paused) {
      $("#progress-title").textContent = "已暂停";
    } else if (processing) {
      $("#progress-title").textContent = processing.name;
    } else if (state.running) {
      $("#progress-title").textContent = "正在准备 AI 引擎";
    } else {
      $("#progress-title").textContent = "批处理完成";
    }
    $("#batch-footer-status").textContent = state.running
      ? `${values.finished} 张已完成 · 原片永不覆盖`
      : "处理结束 · 原片永不覆盖";
    updateFollowingState(state);
    updateInspector(jobById(state.selectedId));
  }

  function selectJob(identifier, pin) {
    const job = jobById(identifier);
    if (!job) return;
    PlateApp.store.patch({
      selectedId: identifier,
      previewMode: pin ? "pinned" : PlateApp.store.get().previewMode
    }, "job_selected");
    renderState();
    PlateApp.preview.show(job);
    PlateApp.filmstrip.ensureVisible(identifier);
  }

  function restoreFollowing() {
    const state = PlateApp.store.get();
    const target = state.processingId || state.selectedId || state.jobs[0]?.job_id || null;
    PlateApp.store.patch({
      previewMode: "following",
      selectedId: target
    }, "follow_restored");
    renderState();
    if (target) {
      PlateApp.preview.show(jobById(target));
      PlateApp.filmstrip.ensureVisible(target);
    }
  }

  function setDetailsOpen(open) {
    const inspector = $("#job-inspector");
    const toggle = $("#details-toggle");
    inspector.classList.toggle("is-open", open);
    toggle.setAttribute("aria-expanded", String(open));
    if (open) {
      detailsRestoreFocus = document.activeElement;
      window.setTimeout(() => $("#details-close-button").focus(), 0);
    } else if (detailsRestoreFocus && document.contains(detailsRestoreFocus)) {
      detailsRestoreFocus.focus();
      detailsRestoreFocus = null;
    }
  }

  async function start(paths) {
    if (!paths || !paths.length) return;
    try {
      const response = await PlateApp.bridge.call("start_batch", paths);
      if (!response.accepted) PlateApp.toast.show(response.message);
    } catch (error) {
      PlateApp.toast.show(`无法开始批处理：${error.message || error}`);
    }
  }

  async function chooseFiles() {
    try {
      const paths = await PlateApp.bridge.call("choose_files");
      await start(paths);
    } catch (error) {
      PlateApp.toast.show(`无法选择照片：${error.message || error}`);
    }
  }

  async function chooseFolder() {
    try {
      const paths = await PlateApp.bridge.call("choose_folder");
      await start(paths);
    } catch (error) {
      PlateApp.toast.show(`无法选择文件夹：${error.message || error}`);
    }
  }

  function announce(message) {
    const region = $("#live-region");
    region.textContent = "";
    window.setTimeout(() => {
      region.textContent = message;
    }, 20);
  }

  function receiveBackendEvent(event) {
    PlateApp.store.dispatch(event);
    const payload = event.payload || {};
    switch (event.name) {
      case "batch_accepted":
        announce("批处理已开始。");
        break;
      case "batch_items_ready": {
        const first = PlateApp.store.get().jobs[0];
        if (first) selectJob(first.job_id, false);
        PlateApp.filmstrip.render();
        break;
      }
      case "item_started":
        if (PlateApp.store.get().previewMode === "following") {
          selectJob(String(payload.job_id), false);
        }
        break;
      case "item_finished": {
        PlateApp.preview.invalidate(String(payload.job_id), "result");
        PlateApp.filmstrip.invalidate(String(payload.job_id));
        if (PlateApp.store.get().selectedId === String(payload.job_id)) {
          PlateApp.preview.show(jobById(String(payload.job_id)));
        }
        if (payload.status === "review_required") {
          PlateApp.review && PlateApp.review.refresh();
        }
        break;
      }
      case "paused":
        announce(payload.paused ? "批处理已暂停。" : "批处理已继续。");
        break;
      case "fatal_error":
        PlateApp.toast.show(payload.message);
        announce(`批处理无法继续：${payload.message}`);
        break;
      case "batch_finished":
        announce(payload.cancelled ? "剩余任务已取消。" : "批处理已完成。");
        if (!payload.cancelled && PlateApp.store.get().total > 0) {
          PlateApp.toast.show("批处理完成，原片未被覆盖。");
        }
        PlateApp.history && PlateApp.history.refresh();
        break;
      default:
        break;
    }
    renderState();
  }

  async function cancelBatch() {
    const accepted = await PlateApp.dialog.confirm({
      title: "取消剩余任务？",
      description: "当前正在处理的照片会安全完成，尚未开始的任务将取消。",
      confirmLabel: "取消剩余"
    });
    if (!accepted) return;
    try {
      await PlateApp.bridge.call("cancel");
    } catch (error) {
      PlateApp.toast.show(`无法取消剩余任务：${error.message || error}`);
    }
  }

  function init() {
    $("#choose-files").addEventListener("click", chooseFiles);
    $("#choose-folder").addEventListener("click", chooseFolder);
    $("#add-files-button").addEventListener("click", chooseFiles);
    $("#pause-button").addEventListener("click", async () => {
      const state = PlateApp.store.get();
      const button = $("#pause-button");
      button.disabled = true;
      try {
        await PlateApp.bridge.call(state.paused ? "resume" : "pause");
      } catch (error) {
        PlateApp.toast.show(`无法${state.paused ? "继续" : "暂停"}批处理：${error.message || error}`);
      } finally {
        renderState();
      }
    });
    $("#cancel-button").addEventListener("click", cancelBatch);
    $("#review-button").addEventListener("click", () => PlateApp.navigate("review"));
    $("#restore-follow-button").addEventListener("click", restoreFollowing);
    $("#details-toggle").addEventListener("click", () => setDetailsOpen(true));
    $("#details-close-button").addEventListener("click", () => setDetailsOpen(false));
    window.addEventListener("keydown", (event) => {
      if (
        event.key === "Escape" &&
        $("#job-inspector").classList.contains("is-open")
      ) {
        event.preventDefault();
        setDetailsOpen(false);
      }
    });
    $("#open-job-output-button").addEventListener("click", async () => {
      const identifier = PlateApp.store.get().selectedId;
      if (!identifier) return;
      try {
        if (await PlateApp.bridge.call("open_job_output", identifier)) return;
        PlateApp.toast.show("输出文件夹暂不可用。");
      } catch (error) {
        PlateApp.toast.show(`无法打开输出文件夹：${error.message || error}`);
      }
    });
    $("#inspector-review-button").addEventListener("click", () => {
      const identifier = PlateApp.store.get().selectedId;
      if (!identifier) return;
      PlateApp.navigate("review");
      window.setTimeout(() => PlateApp.review.load(identifier), 0);
    });
    $("#inspector-retry-button").addEventListener("click", async () => {
      const identifier = PlateApp.store.get().selectedId;
      if (!identifier) return;
      try {
        const response = await PlateApp.bridge.call("retry_job", identifier);
        PlateApp.toast.show(response.message);
      } catch (error) {
        PlateApp.toast.show(`无法重新处理：${error.message || error}`);
      }
    });

    const dropZone = $("#drop-zone");
    ["dragenter", "dragover"].forEach((name) => {
      dropZone.addEventListener(name, (event) => {
        event.preventDefault();
        if (!PlateApp.store.get().running) dropZone.classList.add("is-dragging");
      });
    });
    ["dragleave", "drop"].forEach((name) => {
      dropZone.addEventListener(name, (event) => {
        event.preventDefault();
        dropZone.classList.remove("is-dragging");
      });
    });
  }

  PlateApp.batch = {
    chooseFiles,
    init,
    receiveBackendEvent,
    renderState,
    restoreFollowing,
    setDetailsOpen,
    selectJob,
    start
  };
})();
