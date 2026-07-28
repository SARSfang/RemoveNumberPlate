(() => {
  "use strict";

  const state = {
    running: false,
    paused: false,
    total: 0,
    counts: { completed: 0, review_required: 0, failed: 0 },
    rows: new Map(),
    reviewItems: [],
    currentReview: null,
    reviewImage: null,
    commands: [],
    redoCommands: [],
    previewCommand: null,
    tool: "rectangle",
    brushSize: 36,
    view: { scale: 1, x: 0, y: 0 },
    pointer: null,
    spaceDown: false,
    toastTimer: null
  };

  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => [...document.querySelectorAll(selector)];

  function showToast(message) {
    const toast = $("#toast");
    toast.textContent = message;
    toast.hidden = false;
    window.clearTimeout(state.toastTimer);
    state.toastTimer = window.setTimeout(() => { toast.hidden = true; }, 4200);
  }

  function setPage(name) {
    $$(".nav-item").forEach((button) => button.classList.toggle("is-active", button.dataset.page === name));
    $$(".page").forEach((page) => page.classList.toggle("is-active", page.id === `page-${name}`));
    const heading = $(`#page-${name} h1`);
    if (heading) heading.focus({ preventScroll: true });
    if (name === "review") refreshReviewJobs();
    if (name === "history") refreshHistory();
  }

  function setProgress(value) {
    const safe = Math.max(0, Math.min(100, value));
    $("#progress-fill").style.width = `${safe}%`;
    const track = $(".progress-track");
    track.setAttribute("aria-valuenow", String(safe));
  }

  function updateStats() {
    $("#stat-total").textContent = state.total;
    $("#stat-completed").textContent = state.counts.completed;
    $("#stat-review").textContent = state.counts.review_required;
    $("#stat-processing").textContent = state.running && state.total ? "1" : "0";
    $("#stat-failed").textContent = state.counts.failed;
    const badge = $("#review-badge");
    badge.textContent = state.counts.review_required;
    badge.hidden = state.counts.review_required === 0;
    $("#review-button").disabled = state.counts.review_required === 0;
  }

  function resetBatch() {
    state.running = true;
    state.paused = false;
    state.total = 0;
    state.counts = {
      completed: 0,
      review_required: state.reviewItems.length,
      failed: 0
    };
    state.rows.clear();
    $("#task-rows").innerHTML = "";
    $("#progress-title").textContent = "正在准备 AI 模型…";
    $("#progress-count").textContent = "0 / 0";
    $("#pause-button").textContent = "暂停";
    $("#pause-button").disabled = false;
    $("#cancel-button").disabled = false;
    $("#drop-zone").classList.add("is-disabled");
    setProgress(0);
    updateStats();
  }

  async function startBatch(paths) {
    if (!paths || paths.length === 0) return;
    const response = await window.pywebview.api.start_batch(paths);
    if (!response.accepted) {
      showToast(response.message);
    }
  }

  function addTaskRow(payload) {
    const tbody = $("#task-rows");
    const row = document.createElement("tr");
    row.innerHTML = `
      <td title=""></td>
      <td><span class="status status-detecting">处理中</span></td>
      <td>—</td>
      <td>—</td>`;
    row.cells[0].textContent = payload.name;
    row.cells[0].title = payload.source;
    tbody.appendChild(row);
    state.rows.set(payload.source, row);
    row.scrollIntoView({ block: "nearest" });
  }

  function finishTaskRow(payload) {
    const row = state.rows.get(payload.source);
    if (!row) return;
    const labels = {
      completed: "已完成",
      review_required: "待复核",
      no_plate: "未发现车牌",
      failed: "失败"
    };
    row.cells[1].innerHTML = "";
    const status = document.createElement("span");
    status.className = `status status-${payload.status}`;
    status.textContent = labels[payload.status] || "已跳过";
    row.cells[1].appendChild(status);
    row.cells[2].textContent = `${Number(payload.elapsed).toFixed(2)} 秒`;
    if (payload.output) {
      const button = document.createElement("button");
      button.className = "output-link";
      button.type = "button";
      button.textContent = "打开";
      button.addEventListener("click", () => window.pywebview.api.open_output(payload.output));
      row.cells[3].textContent = "";
      row.cells[3].appendChild(button);
    }
    if (Object.hasOwn(state.counts, payload.status)) state.counts[payload.status] += 1;
    if (payload.status === "review_required") {
      if (!state.reviewItems.some((item) => item.id === payload.job_id)) {
        state.reviewItems.push({
          id: payload.job_id,
          name: payload.name,
          source: payload.source,
          risks: payload.risks,
          detection_count: 0
        });
      }
      renderReview();
    }
  }

  function renderReview() {
    const list = $("#review-list");
    const empty = $("#review-empty");
    const workspace = $("#review-workspace");
    if (state.reviewItems.length === 0) {
      empty.hidden = false;
      workspace.hidden = true;
      state.currentReview = null;
      return;
    }
    empty.hidden = true;
    workspace.hidden = false;
    $("#review-queue-count").textContent = state.reviewItems.length;
    list.innerHTML = "";
    state.reviewItems.forEach((item) => {
      const card = document.createElement("button");
      card.type = "button";
      card.className = "review-item";
      card.classList.toggle("is-active", state.currentReview?.id === item.id);
      const title = document.createElement("strong");
      title.textContent = item.name;
      const detail = document.createElement("span");
      detail.textContent = `${item.detection_count || 0} 个候选区域 · 原图未修改`;
      card.append(title, detail);
      card.addEventListener("click", () => loadReview(item.id));
      list.appendChild(card);
    });
    if (!state.currentReview) loadReview(state.reviewItems[0].id);
  }

  async function refreshReviewJobs() {
    if (!window.pywebview?.api?.list_review_jobs) return;
    state.reviewItems = await window.pywebview.api.list_review_jobs();
    state.counts.review_required = state.reviewItems.length;
    renderReview();
    updateStats();
  }

  function statusLabel(status) {
    return {
      queued: "排队中",
      detecting: "检测中",
      inpainting: "修复中",
      writing: "写入中",
      completed: "已完成",
      review_required: "待复核",
      no_plate: "未发现车牌",
      failed: "失败",
      cancelled: "已取消"
    }[status] || status;
  }

  function historyAction(label, action) {
    const button = document.createElement("button");
    button.className = "output-link";
    button.type = "button";
    button.textContent = label;
    button.addEventListener("click", action);
    return button;
  }

  async function refreshHistory() {
    if (!window.pywebview?.api?.list_history) return;
    const jobs = await window.pywebview.api.list_history(100);
    const rows = $("#history-rows");
    rows.innerHTML = "";
    $("#history-total").textContent = jobs.length;
    if (!jobs.length) {
      rows.innerHTML = '<tr class="empty-row"><td colspan="4">还没有本机任务记录。</td></tr>';
      return;
    }
    jobs.forEach((job) => {
      const row = document.createElement("tr");
      const name = document.createElement("td");
      name.textContent = job.name;
      if (job.error) name.title = job.error;
      const statusCell = document.createElement("td");
      const status = document.createElement("span");
      status.className = `status status-${job.status}`;
      status.textContent = statusLabel(job.status);
      statusCell.appendChild(status);
      const updated = document.createElement("td");
      const date = new Date(job.updated_at);
      updated.textContent = Number.isNaN(date.getTime()) ? "—" : date.toLocaleString("zh-CN");
      const actions = document.createElement("td");
      const actionWrap = document.createElement("div");
      actionWrap.className = "history-actions";
      if (job.output) {
        actionWrap.appendChild(historyAction(
          "打开输出",
          () => window.pywebview.api.open_output(job.output)
        ));
      }
      if (job.status === "review_required") {
        actionWrap.appendChild(historyAction("进入复核", () => {
          setPage("review");
          window.setTimeout(() => loadReview(job.id), 0);
        }));
      }
      if (job.status === "no_plate") {
        actionWrap.appendChild(historyAction("手动标记", async () => {
          const result = await window.pywebview.api.queue_for_manual_review(job.id);
          showToast(result.message);
          if (result.accepted) {
            await refreshReviewJobs();
            await refreshHistory();
          }
        }));
      }
      if (["queued", "failed", "cancelled"].includes(job.status)) {
        actionWrap.appendChild(historyAction("重新处理", async () => {
          const result = await window.pywebview.api.retry_job(job.id);
          showToast(result.message);
          if (result.accepted) setPage("batch");
        }));
      }
      actions.appendChild(actionWrap);
      row.append(name, statusCell, updated, actions);
      rows.appendChild(row);
    });
  }

  function moveReview(direction) {
    if (!state.currentReview || state.reviewItems.length < 2) return;
    const index = state.reviewItems.findIndex((item) => item.id === state.currentReview.id);
    const next = (index + direction + state.reviewItems.length) % state.reviewItems.length;
    loadReview(state.reviewItems[next].id);
  }

  async function loadReview(identifier) {
    $("#canvas-loading").hidden = false;
    try {
      const review = await window.pywebview.api.get_review_job(identifier);
      const image = new Image();
      await new Promise((resolve, reject) => {
        image.onload = resolve;
        image.onerror = reject;
        image.src = review.image;
      });
      state.currentReview = review;
      state.reviewImage = image;
      state.commands = Array.isArray(review.commands) ? review.commands : [];
      state.redoCommands = [];
      state.previewCommand = null;
      $("#review-file-name").textContent = review.name;
      $("#review-risk-text").textContent = riskDescription(review.risks);
      fitReviewImage();
      updateEditorButtons();
      renderReview();
    } catch (error) {
      showToast(`无法载入复核照片：${error.message || error}`);
    } finally {
      $("#canvas-loading").hidden = true;
    }
  }

  function riskDescription(risks) {
    const labels = {
      low_confidence: "检测置信度较低",
      plate_too_small: "车牌区域过小",
      touches_edge: "车牌靠近画面边缘",
      abnormal_box: "检测框比例异常",
      overlapping_boxes: "多个候选区域重叠"
    };
    const values = (risks || []).map((risk) => labels[risk] || "检测存在风险");
    return `${values.join(" · ") || "检测存在风险"}，原图尚未修改`;
  }

  function canvasMetrics() {
    const canvas = $("#review-canvas");
    const ratio = window.devicePixelRatio || 1;
    const width = Math.max(canvas.clientWidth, 1);
    const height = Math.max(canvas.clientHeight, 1);
    if (canvas.width !== Math.round(width * ratio) || canvas.height !== Math.round(height * ratio)) {
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
    }
    return { canvas, ratio, width, height };
  }

  function fitReviewImage() {
    if (!state.currentReview) return;
    const { width, height } = canvasMetrics();
    state.view.scale = Math.min(
      width / state.currentReview.width,
      height / state.currentReview.height
    ) * 0.94;
    state.view.x = (width - state.currentReview.width * state.view.scale) / 2;
    state.view.y = (height - state.currentReview.height * state.view.scale) / 2;
    drawReview();
  }

  function sourcePoint(event) {
    const rect = $("#review-canvas").getBoundingClientRect();
    return [
      (event.clientX - rect.left - state.view.x) / state.view.scale,
      (event.clientY - rect.top - state.view.y) / state.view.scale
    ];
  }

  function drawReview() {
    if (!state.currentReview || !state.reviewImage) return;
    const { canvas, ratio, width, height } = canvasMetrics();
    const context = canvas.getContext("2d");
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.clearRect(0, 0, width, height);
    context.fillStyle = "#070A10";
    context.fillRect(0, 0, width, height);
    context.save();
    context.translate(state.view.x, state.view.y);
    context.scale(state.view.scale, state.view.scale);
    context.imageSmoothingQuality = "high";
    context.drawImage(
      state.reviewImage,
      0,
      0,
      state.currentReview.width,
      state.currentReview.height
    );
    context.restore();
    drawMaskOverlay(context, ratio, width, height);
  }

  function drawMaskOverlay(context, ratio, width, height) {
    const overlay = document.createElement("canvas");
    overlay.width = Math.round(width * ratio);
    overlay.height = Math.round(height * ratio);
    const layer = overlay.getContext("2d");
    layer.setTransform(ratio, 0, 0, ratio, 0, 0);
    layer.translate(state.view.x, state.view.y);
    layer.scale(state.view.scale, state.view.scale);
    const commands = [...state.commands];
    if (state.previewCommand) commands.push(state.previewCommand);
    const removed = new Set(
      commands.filter((command) => command.type === "remove_detection").map((command) => command.index)
    );
    layer.fillStyle = "rgba(240, 180, 76, .32)";
    layer.strokeStyle = "rgba(255, 211, 132, .96)";
    layer.lineWidth = 2 / state.view.scale;
    state.currentReview.detections.forEach((detection, index) => {
      if (removed.has(index)) return;
      const boxHeight = detection.y2 - detection.y1;
      const x = Math.max(0, detection.x1 - boxHeight * .95);
      const y = Math.max(0, detection.y1 - boxHeight * .4);
      const x2 = Math.min(state.currentReview.width, detection.x2 + boxHeight);
      const y2 = Math.min(state.currentReview.height, detection.y2 + boxHeight * .4);
      layer.fillRect(x, y, x2 - x, y2 - y);
      layer.setLineDash([8 / state.view.scale, 5 / state.view.scale]);
      layer.strokeRect(x, y, x2 - x, y2 - y);
      layer.setLineDash([]);
    });
    commands.forEach((command) => drawCommand(layer, command));
    context.setTransform(1, 0, 0, 1, 0, 0);
    context.drawImage(overlay, 0, 0);
  }

  function drawCommand(context, command) {
    if (command.type === "rectangle") {
      const x = Math.min(command.start[0], command.end[0]);
      const y = Math.min(command.start[1], command.end[1]);
      const width = Math.abs(command.end[0] - command.start[0]);
      const height = Math.abs(command.end[1] - command.start[1]);
      context.fillStyle = "rgba(76, 141, 255, .35)";
      context.strokeStyle = "#8DB6FF";
      context.lineWidth = 2 / state.view.scale;
      context.fillRect(x, y, width, height);
      context.strokeRect(x, y, width, height);
    } else if (command.type === "brush_add" || command.type === "brush_erase") {
      const points = command.points || [];
      if (!points.length) return;
      context.save();
      context.lineCap = "round";
      context.lineJoin = "round";
      context.lineWidth = command.radius * 2;
      if (command.type === "brush_erase") {
        context.globalCompositeOperation = "destination-out";
        context.strokeStyle = "#000";
      } else {
        context.strokeStyle = "rgba(76, 141, 255, .46)";
      }
      context.beginPath();
      context.moveTo(points[0][0], points[0][1]);
      points.slice(1).forEach((point) => context.lineTo(point[0], point[1]));
      if (points.length === 1) context.lineTo(points[0][0] + .01, points[0][1]);
      context.stroke();
      context.restore();
    }
  }

  function commitCommand(command) {
    state.commands.push(command);
    state.redoCommands = [];
    state.previewCommand = null;
    updateEditorButtons();
    drawReview();
  }

  function updateEditorButtons() {
    $("#undo-button").disabled = state.commands.length === 0;
    $("#redo-button").disabled = state.redoCommands.length === 0;
  }

  function findDetection(point) {
    if (!state.currentReview) return -1;
    return state.currentReview.detections.findIndex((detection) =>
      point[0] >= detection.x1 && point[0] <= detection.x2 &&
      point[1] >= detection.y1 && point[1] <= detection.y2
    );
  }

  function receiveBackendEvent(event) {
    const payload = event.payload;
    switch (event.name) {
      case "batch_accepted":
        resetBatch();
        break;
      case "batch_discovered":
        state.total = payload.total;
        $("#progress-count").textContent = `0 / ${state.total}`;
        updateStats();
        break;
      case "item_started":
        $("#progress-title").textContent = payload.name;
        $("#progress-count").textContent = `${payload.index - 1} / ${payload.total}`;
        addTaskRow(payload);
        break;
      case "item_finished":
        finishTaskRow(payload);
        $("#progress-count").textContent = `${payload.index} / ${payload.total}`;
        setProgress(Math.round(payload.index / payload.total * 100));
        updateStats();
        break;
      case "paused":
        state.paused = payload.paused;
        $("#pause-button").textContent = state.paused ? "继续" : "暂停";
        if (state.paused) $("#progress-title").textContent = "已暂停";
        break;
      case "fatal_error":
        $("#progress-title").textContent = "无法继续";
        showToast(payload.message);
        break;
      case "batch_finished":
        state.running = false;
        $("#progress-title").textContent = payload.cancelled ? "已取消剩余任务" : "批处理完成";
        $("#pause-button").disabled = true;
        $("#cancel-button").disabled = true;
        $("#drop-zone").classList.remove("is-disabled");
        updateStats();
        if (!payload.cancelled && state.total > 0) showToast("批处理完成，原片未被覆盖。");
        refreshHistory();
        break;
      case "review_started":
        $("#confirm-review-button").disabled = true;
        $("#skip-review-button").disabled = true;
        $("#review-risk-text").textContent = "正在按人工掩码重修…";
        break;
      case "review_finished":
        state.reviewItems = state.reviewItems.filter((item) => item.id !== payload.job_id);
        state.currentReview = null;
        state.counts.review_required = state.reviewItems.length;
        renderReview();
        updateStats();
        showToast(`重修完成，用时 ${Number(payload.elapsed).toFixed(2)} 秒。`);
        refreshHistory();
        break;
      case "review_failed":
        $("#confirm-review-button").disabled = false;
        $("#skip-review-button").disabled = false;
        $("#review-risk-text").textContent = "重修失败，人工编辑已经保留";
        showToast(`重修失败：${payload.message}`);
        break;
      case "review_skipped":
        state.reviewItems = state.reviewItems.filter((item) => item.id !== payload.job_id);
        state.currentReview = null;
        state.counts.review_required = state.reviewItems.length;
        renderReview();
        updateStats();
        showToast("已跳过此图，原片未修改。");
        refreshHistory();
        break;
      case "history_changed":
        refreshHistory();
        break;
    }
  }

  window.app = { receiveBackendEvent };

  window.addEventListener("pywebviewready", async () => {
    const bootstrap = await window.pywebview.api.bootstrap();
    $("#app-version").textContent = bootstrap.version;
    $("#gpu-name").textContent = bootstrap.gpu;
    $("#runtime-name").textContent = bootstrap.runtime;
    $("#model-state").textContent = bootstrap.models_ready ? "已校验，可以处理" : "模型缺失或校验失败";
    $("#model-state").style.color = bootstrap.models_ready ? "var(--success)" : "var(--danger)";
    $("#webview2-version").textContent = bootstrap.webview2_version;
    $("#preset").value = bootstrap.preset || "balanced";
    const counts = bootstrap.history_counts || {};
    $("#history-total").textContent = Object.values(counts).reduce((sum, value) => sum + value, 0);
    await refreshReviewJobs();
    await refreshHistory();
    if (bootstrap.recovered_jobs > 0) {
      showToast(`发现 ${bootstrap.recovered_jobs} 个中断任务，可在任务历史中重新处理。`);
    }
    await window.pywebview.api.frontend_ready();
  });

  $$(".nav-item").forEach((button) => button.addEventListener("click", () => setPage(button.dataset.page)));
  $$("[data-go-page]").forEach((button) => button.addEventListener("click", () => setPage(button.dataset.goPage)));
  $("#review-button").addEventListener("click", () => setPage("review"));
  $("#choose-files").addEventListener("click", async () => startBatch(await window.pywebview.api.choose_files()));
  $("#choose-folder").addEventListener("click", async () => startBatch(await window.pywebview.api.choose_folder()));
  $("#pause-button").addEventListener("click", async () => {
    if (state.paused) await window.pywebview.api.resume();
    else await window.pywebview.api.pause();
  });
  $("#cancel-button").addEventListener("click", () => window.pywebview.api.cancel());
  $("#refresh-history-button").addEventListener("click", refreshHistory);
  $("#preset").addEventListener("change", async (event) => {
    const response = await window.pywebview.api.set_preset(event.target.value);
    showToast(response.message);
    if (!response.accepted) {
      const bootstrap = await window.pywebview.api.bootstrap();
      event.target.value = bootstrap.preset || "balanced";
    }
  });
  $("#export-diagnostics-button").addEventListener("click", async () => {
    const response = await window.pywebview.api.export_diagnostics();
    if (response.message) showToast(response.message);
  });

  $$(".tool-button[data-tool]").forEach((button) => button.addEventListener("click", () => {
    state.tool = button.dataset.tool;
    $$(".tool-button[data-tool]").forEach((value) => value.classList.toggle("is-active", value === button));
    $("#review-canvas").style.cursor = state.tool === "remove_detection" ? "not-allowed" : "crosshair";
  }));
  $("#brush-size").addEventListener("input", (event) => {
    state.brushSize = Number(event.target.value);
    $("#brush-size-value").textContent = state.brushSize;
  });
  $("#undo-button").addEventListener("click", () => {
    if (!state.commands.length) return;
    state.redoCommands.push(state.commands.pop());
    updateEditorButtons();
    drawReview();
  });
  $("#redo-button").addEventListener("click", () => {
    if (!state.redoCommands.length) return;
    state.commands.push(state.redoCommands.pop());
    updateEditorButtons();
    drawReview();
  });
  $("#restore-button").addEventListener("click", () => {
    state.redoCommands = [...state.commands].reverse();
    state.commands = [];
    updateEditorButtons();
    drawReview();
  });
  $("#confirm-review-button").addEventListener("click", async () => {
    if (!state.currentReview) return;
    const response = await window.pywebview.api.reprocess_review(
      state.currentReview.id,
      state.commands
    );
    if (!response.accepted) showToast(response.message);
  });
  $("#skip-review-button").addEventListener("click", async () => {
    if (!state.currentReview) return;
    await window.pywebview.api.skip_review(state.currentReview.id);
  });
  $("#previous-review-button").addEventListener("click", () => moveReview(-1));
  $("#next-review-button").addEventListener("click", () => moveReview(1));

  const reviewCanvas = $("#review-canvas");
  reviewCanvas.addEventListener("pointerdown", (event) => {
    if (!state.currentReview) return;
    reviewCanvas.setPointerCapture(event.pointerId);
    const point = sourcePoint(event);
    if (event.button === 1 || state.spaceDown) {
      state.pointer = { type: "pan", x: event.clientX, y: event.clientY, viewX: state.view.x, viewY: state.view.y };
      reviewCanvas.style.cursor = "grabbing";
      return;
    }
    if (state.tool === "remove_detection") {
      const index = findDetection(point);
      if (index >= 0 && !state.commands.some((command) => command.type === "remove_detection" && command.index === index)) {
        commitCommand({ type: "remove_detection", index });
      }
      return;
    }
    if (state.tool === "rectangle") {
      state.pointer = { type: "rectangle", start: point };
      state.previewCommand = { type: "rectangle", start: point, end: point };
    } else {
      state.pointer = { type: state.tool, points: [point] };
      state.previewCommand = { type: state.tool, points: [point], radius: state.brushSize };
    }
  });
  reviewCanvas.addEventListener("pointermove", (event) => {
    if (!state.pointer) return;
    if (state.pointer.type === "pan") {
      state.view.x = state.pointer.viewX + event.clientX - state.pointer.x;
      state.view.y = state.pointer.viewY + event.clientY - state.pointer.y;
    } else {
      const point = sourcePoint(event);
      if (state.pointer.type === "rectangle") {
        state.previewCommand.end = point;
      } else {
        const points = state.previewCommand.points;
        const previous = points[points.length - 1];
        if (Math.hypot(point[0] - previous[0], point[1] - previous[1]) > 2 / state.view.scale) {
          points.push(point);
        }
      }
    }
    drawReview();
  });
  reviewCanvas.addEventListener("pointerup", () => {
    if (!state.pointer) return;
    if (state.pointer.type !== "pan" && state.previewCommand) {
      commitCommand(state.previewCommand);
    }
    state.pointer = null;
    state.previewCommand = null;
    reviewCanvas.style.cursor = state.spaceDown ? "grab" : "crosshair";
    drawReview();
  });
  reviewCanvas.addEventListener("wheel", (event) => {
    if (!state.currentReview) return;
    event.preventDefault();
    const rect = reviewCanvas.getBoundingClientRect();
    const mouseX = event.clientX - rect.left;
    const mouseY = event.clientY - rect.top;
    const sourceX = (mouseX - state.view.x) / state.view.scale;
    const sourceY = (mouseY - state.view.y) / state.view.scale;
    const factor = event.deltaY < 0 ? 1.12 : .89;
    state.view.scale = Math.max(.03, Math.min(8, state.view.scale * factor));
    state.view.x = mouseX - sourceX * state.view.scale;
    state.view.y = mouseY - sourceY * state.view.scale;
    drawReview();
  }, { passive: false });
  window.addEventListener("keydown", (event) => {
    if (event.code === "Space" && !event.repeat) {
      state.spaceDown = true;
      reviewCanvas.style.cursor = "grab";
    }
    if (event.ctrlKey && event.key.toLowerCase() === "z") {
      event.preventDefault();
      $("#undo-button").click();
    } else if (event.ctrlKey && event.key.toLowerCase() === "y") {
      event.preventDefault();
      $("#redo-button").click();
    } else if (!event.ctrlKey && ["r", "b", "e"].includes(event.key.toLowerCase())) {
      const tool = { r: "rectangle", b: "brush_add", e: "brush_erase" }[event.key.toLowerCase()];
      $(`.tool-button[data-tool="${tool}"]`).click();
    } else if (!event.ctrlKey && event.key === "[") {
      moveReview(-1);
    } else if (!event.ctrlKey && event.key === "]") {
      moveReview(1);
    }
  });
  window.addEventListener("keyup", (event) => {
    if (event.code === "Space") {
      state.spaceDown = false;
      reviewCanvas.style.cursor = "crosshair";
    }
  });
  new ResizeObserver(() => {
    if (state.currentReview) drawReview();
  }).observe($("#canvas-stage"));

  const dropZone = $("#drop-zone");
  ["dragenter", "dragover"].forEach((name) => dropZone.addEventListener(name, (event) => {
    event.preventDefault();
    if (!state.running) dropZone.classList.add("is-dragging");
  }));
  ["dragleave", "drop"].forEach((name) => dropZone.addEventListener(name, (event) => {
    event.preventDefault();
    dropZone.classList.remove("is-dragging");
  }));
})();
