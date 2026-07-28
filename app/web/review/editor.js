(function () {
  "use strict";
  const PlateApp = window.PlateApp = window.PlateApp || {};
  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => [...document.querySelectorAll(selector)];
  const state = {
    items: [],
    current: null,
    image: null,
    commands: [],
    redoCommands: [],
    previewCommand: null,
    tool: "rectangle",
    brushSize: 36,
    maskOpacity: .36,
    view: { scale: 1, x: 0, y: 0 },
    pointer: null,
    spaceDown: false,
    dirty: false,
    loadingId: null
  };
  let loadSerial = 0;
  let refreshSerial = 0;

  function updateBadge() {
    const badge = $("#review-badge");
    badge.textContent = state.items.length;
    badge.hidden = state.items.length === 0;
  }

  function render() {
    const list = $("#review-list");
    const empty = $("#review-empty");
    const workspace = $("#review-workspace");
    updateBadge();
    if (!state.items.length) {
      empty.hidden = false;
      workspace.hidden = true;
      state.current = null;
      return;
    }
    empty.hidden = true;
    workspace.hidden = false;
    $("#review-queue-count").textContent = state.items.length;
    list.replaceChildren();
    state.items.forEach((item) => {
      const card = document.createElement("button");
      card.type = "button";
      card.className = "review-item";
      card.classList.toggle("is-active", state.current && state.current.id === item.id);
      const title = document.createElement("strong");
      title.textContent = item.name;
      const detail = document.createElement("span");
      detail.textContent = `${item.detection_count || 0} 个候选区域 · 原图未修改`;
      card.append(title, detail);
      card.addEventListener("click", () => load(item.id));
      list.appendChild(card);
    });
    if (!state.current && !state.loadingId) load(state.items[0].id);
  }

  async function refresh() {
    if (!PlateApp.bridge.api() || !PlateApp.bridge.api().list_review_jobs) return;
    const serial = ++refreshSerial;
    try {
      const items = await PlateApp.bridge.call("list_review_jobs");
      if (serial !== refreshSerial) return;
      state.items = items;
      if (state.current && !state.items.some((item) => item.id === state.current.id)) {
        state.current = null;
        state.dirty = false;
      }
      render();
      activate();
    } catch (error) {
      if (serial !== refreshSerial) return;
      PlateApp.toast.show(`无法刷新待复核列表：${error.message || error}`);
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

  async function confirmDiscard() {
    if (!state.dirty) return true;
    return PlateApp.dialog.confirm({
      title: "放弃未提交的编辑？",
      description: "当前遮罩调整尚未重修，离开后这些调整不会保留。",
      confirmLabel: "放弃编辑"
    });
  }

  function discardEdits() {
    loadSerial += 1;
    state.current = null;
    state.image = null;
    state.commands = [];
    state.redoCommands = [];
    state.previewCommand = null;
    state.pointer = null;
    state.dirty = false;
    state.loadingId = null;
    $("#canvas-loading").hidden = true;
  }

  async function load(identifier, options) {
    if (!identifier || state.loadingId === identifier) return;
    if (
      state.current &&
      state.current.id !== identifier &&
      !(options && options.force) &&
      !await confirmDiscard()
    ) {
      return;
    }
    const serial = ++loadSerial;
    state.loadingId = identifier;
    $("#canvas-loading").hidden = false;
    try {
      const review = await PlateApp.bridge.call("get_review_job", identifier);
      if (serial !== loadSerial) return;
      const image = new Image();
      await new Promise((resolve, reject) => {
        image.onload = resolve;
        image.onerror = reject;
        image.src = review.image;
      });
      if (serial !== loadSerial) return;
      state.current = review;
      state.image = image;
      state.commands = Array.isArray(review.commands) ? review.commands : [];
      state.redoCommands = [];
      state.previewCommand = null;
      state.dirty = false;
      $("#review-file-name").textContent = review.name;
      $("#review-risk-text").textContent = riskDescription(review.risks);
      updateEditorButtons();
      render();
      await new Promise((resolve) => window.requestAnimationFrame(resolve));
      if (serial !== loadSerial) return;
      fitImage();
    } catch (error) {
      if (serial !== loadSerial) return;
      PlateApp.toast.show(`无法载入复核照片：${error.message || error}`);
    } finally {
      if (serial === loadSerial) {
        state.loadingId = null;
        $("#canvas-loading").hidden = true;
      }
    }
  }

  function canvasMetrics() {
    const canvas = $("#review-canvas");
    const ratio = window.devicePixelRatio || 1;
    const width = Math.max(canvas.clientWidth, 1);
    const height = Math.max(canvas.clientHeight, 1);
    if (
      canvas.width !== Math.round(width * ratio) ||
      canvas.height !== Math.round(height * ratio)
    ) {
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
    }
    return { canvas, ratio, width, height };
  }

  function fitImage() {
    if (!state.current) return;
    const { width, height } = canvasMetrics();
    state.view.scale = Math.min(
      width / state.current.width,
      height / state.current.height
    ) * .94;
    state.view.x = (width - state.current.width * state.view.scale) / 2;
    state.view.y = (height - state.current.height * state.view.scale) / 2;
    draw();
  }

  function needsRefit(scale, width, height) {
    return Number.isFinite(scale) && scale < .01 && width > 1 && height > 1;
  }

  function isMeaningfulRectangle(command, scale) {
    if (!command || command.type !== "rectangle" || !Number.isFinite(scale)) {
      return false;
    }
    const width = Math.abs(command.end[0] - command.start[0]) * scale;
    const height = Math.abs(command.end[1] - command.start[1]) * scale;
    return width >= 3 && height >= 3;
  }

  function updateCanvasCursor() {
    const canvas = $("#review-canvas");
    if (state.spaceDown) {
      canvas.style.cursor = "grab";
    } else {
      canvas.style.cursor =
        state.tool === "remove_detection" ? "not-allowed" : "crosshair";
    }
  }

  function activate() {
    window.requestAnimationFrame(() => {
      const canvas = $("#review-canvas");
      if (
        state.current &&
        needsRefit(state.view.scale, canvas.clientWidth, canvas.clientHeight)
      ) {
        fitImage();
      }
    });
  }

  function sourcePoint(event) {
    const rect = $("#review-canvas").getBoundingClientRect();
    return [
      (event.clientX - rect.left - state.view.x) / state.view.scale,
      (event.clientY - rect.top - state.view.y) / state.view.scale
    ];
  }

  function draw() {
    if (!state.current || !state.image) return;
    const { canvas, ratio, width, height } = canvasMetrics();
    const context = canvas.getContext("2d");
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.clearRect(0, 0, width, height);
    context.fillStyle = "#070b12";
    context.fillRect(0, 0, width, height);
    context.save();
    context.translate(state.view.x, state.view.y);
    context.scale(state.view.scale, state.view.scale);
    context.imageSmoothingQuality = "high";
    context.drawImage(state.image, 0, 0, state.current.width, state.current.height);
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
      commands
        .filter((command) => command.type === "remove_detection")
        .map((command) => command.index)
    );
    layer.fillStyle = `rgba(233, 177, 83, ${state.maskOpacity})`;
    layer.strokeStyle = "rgba(255, 215, 143, .96)";
    layer.lineWidth = 2 / state.view.scale;
    state.current.detections.forEach((detection, index) => {
      if (removed.has(index)) return;
      const boxHeight = detection.y2 - detection.y1;
      const x = Math.max(0, detection.x1 - boxHeight * .95);
      const y = Math.max(0, detection.y1 - boxHeight * .4);
      const x2 = Math.min(state.current.width, detection.x2 + boxHeight);
      const y2 = Math.min(state.current.height, detection.y2 + boxHeight * .4);
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
      context.fillStyle = `rgba(78, 139, 255, ${state.maskOpacity})`;
      context.strokeStyle = "#9cbdff";
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
        context.strokeStyle = `rgba(78, 139, 255, ${Math.min(.72, state.maskOpacity + .12)})`;
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
    state.dirty = true;
    updateEditorButtons();
    draw();
  }

  function updateEditorButtons() {
    $("#undo-button").disabled = state.commands.length === 0;
    $("#redo-button").disabled = state.redoCommands.length === 0;
  }

  function findDetection(point) {
    if (!state.current) return -1;
    return state.current.detections.findIndex((detection) =>
      point[0] >= detection.x1 &&
      point[0] <= detection.x2 &&
      point[1] >= detection.y1 &&
      point[1] <= detection.y2
    );
  }

  async function move(direction) {
    if (!state.current || state.items.length < 2) return;
    const index = state.items.findIndex((item) => item.id === state.current.id);
    const next = (index + direction + state.items.length) % state.items.length;
    await load(state.items[next].id);
  }

  function removeCurrent(identifier) {
    state.items = state.items.filter((item) => item.id !== identifier);
    state.current = null;
    state.dirty = false;
    state.loadingId = null;
    render();
  }

  function handleEvent(event) {
    const payload = event.payload || {};
    switch (event.name) {
      case "review_started":
        $("#confirm-review-button").disabled = true;
        $("#skip-review-button").disabled = true;
        $("#review-risk-text").textContent = "正在按人工掩码重修…";
        break;
      case "review_finished":
        removeCurrent(payload.job_id);
        PlateApp.toast.show(`重修完成，用时 ${Number(payload.elapsed).toFixed(2)} 秒。`);
        PlateApp.history && PlateApp.history.refresh();
        break;
      case "review_failed":
        $("#confirm-review-button").disabled = false;
        $("#skip-review-button").disabled = false;
        $("#review-risk-text").textContent = "重修失败，人工编辑已经保留";
        PlateApp.toast.show(`重修失败：${payload.message}`);
        break;
      case "review_skipped":
        removeCurrent(payload.job_id);
        PlateApp.toast.show("已跳过此图，原片未修改。");
        PlateApp.history && PlateApp.history.refresh();
        break;
      case "history_changed":
        refresh();
        break;
      default:
        break;
    }
  }

  function initCanvas() {
    const canvas = $("#review-canvas");
    canvas.addEventListener("pointerdown", (event) => {
      if (!state.current) return;
      if (event.button !== 0 && event.button !== 1) return;
      canvas.setPointerCapture(event.pointerId);
      const point = sourcePoint(event);
      if (event.button === 1 || state.spaceDown) {
        state.pointer = {
          type: "pan",
          x: event.clientX,
          y: event.clientY,
          viewX: state.view.x,
          viewY: state.view.y
        };
        canvas.style.cursor = "grabbing";
        return;
      }
      if (state.tool === "remove_detection") {
        const index = findDetection(point);
        if (
          index >= 0 &&
          !state.commands.some(
            (command) => command.type === "remove_detection" && command.index === index
          )
        ) {
          commitCommand({ type: "remove_detection", index });
        }
        return;
      }
      if (state.tool === "rectangle") {
        state.pointer = { type: "rectangle", start: point };
        state.previewCommand = { type: "rectangle", start: point, end: point };
      } else {
        state.pointer = { type: state.tool, points: [point] };
        state.previewCommand = {
          type: state.tool,
          points: [point],
          radius: state.brushSize
        };
      }
    });
    canvas.addEventListener("pointermove", (event) => {
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
          if (
            Math.hypot(point[0] - previous[0], point[1] - previous[1]) >
            2 / state.view.scale
          ) {
            points.push(point);
          }
        }
      }
      draw();
    });
    function finishPointer(cancelled) {
      if (!state.pointer) return;
      const shouldCommit = (
        !cancelled &&
        state.pointer.type !== "pan" &&
        state.previewCommand &&
        (
          state.previewCommand.type !== "rectangle" ||
          isMeaningfulRectangle(state.previewCommand, state.view.scale)
        )
      );
      if (shouldCommit) {
        commitCommand(state.previewCommand);
      }
      state.pointer = null;
      state.previewCommand = null;
      updateCanvasCursor();
      draw();
    }
    canvas.addEventListener("pointerup", () => finishPointer(false));
    canvas.addEventListener("pointercancel", () => finishPointer(true));
    canvas.addEventListener("lostpointercapture", () => finishPointer(true));
    canvas.addEventListener("contextmenu", (event) => event.preventDefault());
    canvas.addEventListener("wheel", (event) => {
      if (!state.current) return;
      event.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const mouseX = event.clientX - rect.left;
      const mouseY = event.clientY - rect.top;
      const sourceX = (mouseX - state.view.x) / state.view.scale;
      const sourceY = (mouseY - state.view.y) / state.view.scale;
      const factor = event.deltaY < 0 ? 1.12 : .89;
      state.view.scale = Math.max(.03, Math.min(8, state.view.scale * factor));
      state.view.x = mouseX - sourceX * state.view.scale;
      state.view.y = mouseY - sourceY * state.view.scale;
      draw();
    }, { passive: false });
    new ResizeObserver(() => {
      if (state.current) draw();
    }).observe($("#canvas-stage"));
  }

  function init() {
    $$(".tool-button[data-tool]").forEach((button) => {
      button.addEventListener("click", () => {
        state.tool = button.dataset.tool;
        $$(".tool-button[data-tool]").forEach((value) => {
          value.classList.toggle("is-active", value === button);
          value.setAttribute("aria-pressed", value === button ? "true" : "false");
        });
        $("#brush-control").hidden = !["brush_add", "brush_erase"].includes(state.tool);
        updateCanvasCursor();
      });
    });
    $("#brush-size").addEventListener("input", (event) => {
      state.brushSize = Number(event.target.value);
      $("#brush-size-value").textContent = state.brushSize;
    });
    $("#mask-opacity").addEventListener("input", (event) => {
      state.maskOpacity = Number(event.target.value) / 100;
      draw();
    });
    $("#undo-button").addEventListener("click", () => {
      if (!state.commands.length) return;
      state.redoCommands.push(state.commands.pop());
      state.dirty = true;
      updateEditorButtons();
      draw();
    });
    $("#redo-button").addEventListener("click", () => {
      if (!state.redoCommands.length) return;
      state.commands.push(state.redoCommands.pop());
      state.dirty = true;
      updateEditorButtons();
      draw();
    });
    $("#restore-button").addEventListener("click", () => {
      state.redoCommands = [...state.commands].reverse();
      state.commands = [];
      state.dirty = true;
      updateEditorButtons();
      draw();
    });
    $("#confirm-review-button").addEventListener("click", async () => {
      if (!state.current) return;
      const confirmButton = $("#confirm-review-button");
      const skipButton = $("#skip-review-button");
      confirmButton.disabled = true;
      skipButton.disabled = true;
      try {
        const response = await PlateApp.bridge.call(
          "reprocess_review",
          state.current.id,
          state.commands
        );
        if (!response.accepted) {
          PlateApp.toast.show(response.message);
          confirmButton.disabled = false;
          skipButton.disabled = false;
        }
      } catch (error) {
        confirmButton.disabled = false;
        skipButton.disabled = false;
        PlateApp.toast.show(`无法开始重修：${error.message || error}`);
      }
    });
    $("#skip-review-button").addEventListener("click", async () => {
      if (!state.current) return;
      if (state.dirty) {
        const accepted = await PlateApp.dialog.confirm({
          title: "跳过并放弃编辑？",
          description: "当前遮罩调整不会保留，原片仍保持不变。",
          confirmLabel: "跳过此图"
        });
        if (!accepted) return;
      }
      const identifier = state.current.id;
      const button = $("#skip-review-button");
      button.disabled = true;
      try {
        const accepted = await PlateApp.bridge.call("skip_review", identifier);
        if (!accepted) {
          button.disabled = false;
          PlateApp.toast.show("未能跳过此图，请重试。");
        }
      } catch (error) {
        button.disabled = false;
        PlateApp.toast.show(`无法跳过此图：${error.message || error}`);
      }
    });
    $("#previous-review-button").addEventListener("click", () => move(-1));
    $("#next-review-button").addEventListener("click", () => move(1));
    initCanvas();
  }

  PlateApp.review = {
    activate,
    draw,
    discardEdits,
    handleEvent,
    init,
    load,
    isMeaningfulRectangle,
    move,
    needsRefit,
    refresh,
    confirmDiscard,
    state
  };
})();
