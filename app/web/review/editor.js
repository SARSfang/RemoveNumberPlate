(function () {
  "use strict";
  const PlateApp = window.PlateApp = window.PlateApp || {};
  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => [...document.querySelectorAll(selector)];
  const state = {
    mode: "queue",
    items: [],
    current: null,
    image: null,
    resultImage: null,
    commands: [],
    submittedCommands: [],
    redoCommands: [],
    polygons: [],
    selectedPolygonId: null,
    previewCommand: null,
    previewToken: null,
    tool: "polygon",
    brushSize: 36,
    maskOpacity: .36,
    marginRatio: .35,
    viewVariant: "mask",
    phase: "editing",
    view: { scale: 1, x: 0, y: 0 },
    pointer: null,
    spaceDown: false,
    dirty: false,
    loadingId: null
  };
  let loadSerial = 0;
  let refreshSerial = 0;

  function clonePoints(points) {
    return (points || []).map((point) => [Number(point[0]), Number(point[1])]);
  }

  function cross(first, second, third) {
    return (second[0] - first[0]) * (third[1] - second[1]) -
      (second[1] - first[1]) * (third[0] - second[0]);
  }

  function isValidQuadrilateral(points) {
    if (!Array.isArray(points) || points.length !== 4) return false;
    if (!points.every((point) =>
      Array.isArray(point) &&
      point.length === 2 &&
      point.every(Number.isFinite)
    )) return false;
    return points.every((_point, index) =>
      cross(points[index], points[(index + 1) % 4], points[(index + 2) % 4]) > 1e-5
    );
  }

  function pointInPolygon(point, points) {
    if (!Array.isArray(points) || points.length < 3) return false;
    let inside = false;
    for (let index = 0, previous = points.length - 1; index < points.length; previous = index++) {
      const first = points[index];
      const second = points[previous];
      const intersects = ((first[1] > point[1]) !== (second[1] > point[1])) &&
        point[0] < (second[0] - first[0]) * (point[1] - first[1]) /
          (second[1] - first[1] || Number.EPSILON) + first[0];
      if (intersects) inside = !inside;
    }
    return inside;
  }

  function needsRefit(scale, width, height) {
    return Number.isFinite(scale) && scale < .01 && width > 1 && height > 1;
  }

  function isMeaningfulRectangle(command, scale) {
    if (!command || command.type !== "rectangle" || !Number.isFinite(scale)) {
      return false;
    }
    return Math.abs(command.end[0] - command.start[0]) * scale >= 3 &&
      Math.abs(command.end[1] - command.start[1]) * scale >= 3;
  }

  function updateBadge() {
    const badge = $("#review-badge");
    badge.textContent = state.items.length;
    badge.hidden = state.items.length === 0;
  }

  function setMode(mode) {
    state.mode = mode;
    const workspace = $("#review-workspace");
    workspace.classList.toggle("is-single", mode === "single");
    $("#review-sidebar-label").textContent = mode === "single" ? "当前照片" : "待处理";
    $("#review-title").textContent = mode === "single" ? "调整消除区域" : "待复核";
    $("#review-eyebrow").textContent = mode === "single" ? "单张照片精细调整" : "异常照片收件箱";
    $("#review-description").textContent = mode === "single"
      ? "拖动四个角点贴合车牌透视，预览满意后再保存。"
      : "集中处理低置信度、贴边和异常检测。";
    $("#review-privacy-note").textContent = mode === "single"
      ? "临时预览不写入输出"
      : "原图尚未修改";
  }

  function render() {
    const list = $("#review-list");
    const empty = $("#review-empty");
    const workspace = $("#review-workspace");
    updateBadge();
    const hasContent = state.mode === "single" || state.items.length > 0;
    empty.hidden = hasContent;
    workspace.hidden = !hasContent;
    if (!hasContent) {
      state.current = null;
      return;
    }
    $("#review-queue-count").textContent = state.mode === "single" ? "1" : state.items.length;
    list.replaceChildren();
    const items = state.mode === "single" && state.current
      ? [{
          id: state.current.id,
          name: state.current.name,
          detection_count: state.current.detections.length
        }]
      : state.items;
    items.forEach((item) => {
      const card = document.createElement("button");
      card.type = "button";
      card.className = "review-item";
      card.classList.toggle("is-active", state.current && state.current.id === item.id);
      const title = document.createElement("strong");
      title.textContent = item.name || "当前照片";
      const detail = document.createElement("span");
      detail.textContent = `${item.detection_count || 0} 个车牌区域 · 原图未修改`;
      card.append(title, detail);
      if (state.mode === "queue") card.addEventListener("click", () => load(item.id));
      list.appendChild(card);
    });
    if (state.mode === "queue" && !state.current && !state.loadingId) {
      load(state.items[0].id);
    }
  }

  async function refresh() {
    if (state.mode !== "queue") return;
    if (!PlateApp.bridge.api() || !PlateApp.bridge.api().list_review_jobs) return;
    const serial = ++refreshSerial;
    try {
      const items = await PlateApp.bridge.call("list_review_jobs");
      if (serial !== refreshSerial || state.mode !== "queue") return;
      state.items = items;
      if (state.current && !items.some((item) => item.id === state.current.id)) {
        state.current = null;
        state.dirty = false;
      }
      render();
      activate();
    } catch (error) {
      if (serial === refreshSerial) {
        PlateApp.toast.show(`无法刷新待复核列表：${error.message || error}`);
      }
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
    return `${values.join(" · ") || "可拖动四个角点微调"}，原图不会修改`;
  }

  async function confirmDiscard() {
    if (!state.dirty && !state.previewToken) return true;
    return PlateApp.dialog.confirm({
      title: "放弃未保存的调整？",
      description: "临时结果和当前区域调整不会保留，原图与已有结果不受影响。",
      confirmLabel: "放弃调整"
    });
  }

  function resetEditorState() {
    state.current = null;
    state.image = null;
    state.resultImage = null;
    state.commands = [];
    state.submittedCommands = [];
    state.redoCommands = [];
    state.polygons = [];
    state.selectedPolygonId = null;
    state.previewCommand = null;
    state.previewToken = null;
    state.pointer = null;
    state.dirty = false;
    state.loadingId = null;
    state.phase = "editing";
    state.viewVariant = "mask";
    $("#canvas-loading").hidden = true;
  }

  function discardEdits() {
    loadSerial += 1;
    if (state.current) {
      PlateApp.bridge.call("cancel_adjustment", state.current.id).catch(() => {});
    }
    resetEditorState();
    setMode("queue");
  }

  function rebuildPolygons() {
    if (!state.current) return;
    const values = new Map((state.current.detections || []).map((detection, index) => [
      detection.id || `detection:${index}`,
      {
        id: detection.id || `detection:${index}`,
        points: clonePoints(detection.points || [
          [detection.x1, detection.y1],
          [detection.x2, detection.y1],
          [detection.x2, detection.y2],
          [detection.x1, detection.y2]
        ]),
        confidence: Number(detection.confidence || 0),
        manual: false
      }
    ]));
    state.marginRatio = Number(state.current.default_margin_ratio ?? .35);
    state.commands.forEach((command) => {
      if (command.type === "set_detection_polygon" && values.has(command.target_id)) {
        values.get(command.target_id).points = clonePoints(command.points);
      } else if (command.type === "add_polygon") {
        const identifier = `manual:${command.id}`;
        values.set(identifier, {
          id: identifier,
          points: clonePoints(command.points),
          confidence: 1,
          manual: true
        });
      } else if (command.type === "remove_detection") {
        const target = command.target_id || `detection:${command.index}`;
        values.delete(target);
      } else if (command.type === "set_margin") {
        state.marginRatio = Number(command.value ?? command.margin_ratio ?? .35);
      }
    });
    state.polygons = [...values.values()];
    if (!values.has(state.selectedPolygonId)) {
      state.selectedPolygonId = state.polygons[0]?.id || null;
    }
    const percent = Math.round(state.marginRatio * 100);
    $("#mask-margin").value = String(percent);
    $("#mask-margin-value").textContent = `${percent >= 0 ? "+" : ""}${percent}%`;
  }

  async function loadImage(dataUrl) {
    const image = new Image();
    await new Promise((resolve, reject) => {
      image.onload = resolve;
      image.onerror = reject;
      image.src = dataUrl;
    });
    return image;
  }

  async function load(identifier, options) {
    if (!identifier || state.loadingId === identifier) return;
    if (
      state.current &&
      state.current.id !== identifier &&
      !(options && options.force) &&
      !await confirmDiscard()
    ) return;
    if (state.current && state.current.id !== identifier) {
      await PlateApp.bridge.call("cancel_adjustment", state.current.id).catch(() => {});
    }
    const serial = ++loadSerial;
    state.loadingId = identifier;
    $("#canvas-loading").hidden = false;
    try {
      const adjustment = await PlateApp.bridge.call("get_adjustment_job", identifier);
      if (!adjustment.entry_available) throw new Error(adjustment.message);
      const image = await loadImage(adjustment.image);
      if (serial !== loadSerial) return;
      state.current = adjustment;
      state.image = image;
      state.resultImage = null;
      state.commands = Array.isArray(adjustment.commands) ? adjustment.commands : [];
      state.submittedCommands = [];
      state.redoCommands = [];
      state.previewCommand = null;
      state.previewToken = null;
      state.phase = "editing";
      state.viewVariant = "mask";
      state.dirty = false;
      rebuildPolygons();
      $("#review-file-name").textContent = adjustment.name;
      $("#review-risk-text").textContent = riskDescription(adjustment.risks);
      updateEditorButtons();
      render();
      await new Promise((resolve) => window.requestAnimationFrame(resolve));
      if (serial === loadSerial) fitImage();
    } catch (error) {
      if (serial === loadSerial) {
        PlateApp.toast.show(`无法载入照片：${error.message || error}`);
      }
    } finally {
      if (serial === loadSerial) {
        state.loadingId = null;
        $("#canvas-loading").hidden = true;
      }
    }
  }

  async function openSingle(identifier) {
    refreshSerial += 1;
    setMode("single");
    state.items = [];
    render();
    await load(identifier, { force: true });
  }

  function canvasMetrics() {
    const canvas = $("#review-canvas");
    const ratio = window.devicePixelRatio || 1;
    const width = Math.max(canvas.clientWidth, 1);
    const height = Math.max(canvas.clientHeight, 1);
    if (canvas.width !== Math.round(width * ratio) ||
        canvas.height !== Math.round(height * ratio)) {
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

  function activate() {
    window.requestAnimationFrame(() => {
      const canvas = $("#review-canvas");
      if (state.current &&
          needsRefit(state.view.scale, canvas.clientWidth, canvas.clientHeight)) {
        fitImage();
      }
    });
  }

  function clampPoint(point) {
    return [
      Math.max(0, Math.min(state.current.width, point[0])),
      Math.max(0, Math.min(state.current.height, point[1]))
    ];
  }

  function sourcePoint(event) {
    const rect = $("#review-canvas").getBoundingClientRect();
    return clampPoint([
      (event.clientX - rect.left - state.view.x) / state.view.scale,
      (event.clientY - rect.top - state.view.y) / state.view.scale
    ]);
  }

  function expandedPolygon(points, marginRatio) {
    const center = points.reduce(
      (result, point) => [result[0] + point[0] / 4, result[1] + point[1] / 4],
      [0, 0]
    );
    const edges = points.map((point, index) =>
      Math.hypot(
        points[(index + 1) % 4][0] - point[0],
        points[(index + 1) % 4][1] - point[1]
      )
    );
    const shortSide = Math.min((edges[0] + edges[2]) / 2, (edges[1] + edges[3]) / 2);
    const distance = shortSide * marginRatio;
    return points.map((point) => {
      const dx = point[0] - center[0];
      const dy = point[1] - center[1];
      const length = Math.hypot(dx, dy) || 1;
      return [point[0] + dx / length * distance, point[1] + dy / length * distance];
    });
  }

  function tracePolygon(context, points) {
    context.beginPath();
    context.moveTo(points[0][0], points[0][1]);
    points.slice(1).forEach((point) => context.lineTo(point[0], point[1]));
    context.closePath();
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
    const image = state.viewVariant === "result" && state.resultImage
      ? state.resultImage
      : state.image;
    context.drawImage(image, 0, 0, state.current.width, state.current.height);
    if (state.viewVariant === "mask") drawMaskOverlay(context);
    context.restore();
  }

  function drawMaskOverlay(context) {
    state.polygons.forEach((polygon) => {
      const expanded = expandedPolygon(polygon.points, state.marginRatio);
      tracePolygon(context, expanded);
      context.fillStyle = `rgba(233, 177, 83, ${state.maskOpacity})`;
      context.fill();
      tracePolygon(context, polygon.points);
      context.strokeStyle = polygon.id === state.selectedPolygonId ? "#fff0bd" : "#ffd78f";
      context.lineWidth = (polygon.id === state.selectedPolygonId ? 2.5 : 1.5) / state.view.scale;
      context.setLineDash([7 / state.view.scale, 4 / state.view.scale]);
      context.stroke();
      context.setLineDash([]);
      if (polygon.id === state.selectedPolygonId) {
        polygon.points.forEach((point, index) => {
          context.beginPath();
          context.arc(point[0], point[1], 6 / state.view.scale, 0, Math.PI * 2);
          context.fillStyle = "#f7b955";
          context.fill();
          context.strokeStyle = "#171008";
          context.lineWidth = 1.5 / state.view.scale;
          context.stroke();
          context.fillStyle = "#171008";
          context.font = `${9 / state.view.scale}px sans-serif`;
          context.textAlign = "center";
          context.textBaseline = "middle";
          context.fillText(String(index + 1), point[0], point[1]);
        });
      }
    });
    const paintCommands = [...state.commands];
    if (state.previewCommand) paintCommands.push(state.previewCommand);
    paintCommands.forEach((command) => drawPaintCommand(context, command));
  }

  function drawPaintCommand(context, command) {
    if (command.type === "rectangle") {
      const x = Math.min(command.start[0], command.end[0]);
      const y = Math.min(command.start[1], command.end[1]);
      context.fillStyle = `rgba(78, 139, 255, ${state.maskOpacity})`;
      context.fillRect(
        x,
        y,
        Math.abs(command.end[0] - command.start[0]),
        Math.abs(command.end[1] - command.start[1])
      );
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

  function invalidatePreview() {
    if (state.previewToken && state.current) {
      PlateApp.bridge.call("cancel_adjustment", state.current.id).catch(() => {});
    }
    state.previewToken = null;
    state.resultImage = null;
    state.viewVariant = "mask";
    state.phase = "editing";
  }

  function commitCommand(command) {
    invalidatePreview();
    state.commands.push(command);
    state.redoCommands = [];
    state.previewCommand = null;
    state.dirty = true;
    rebuildPolygons();
    updateEditorButtons();
    draw();
  }

  function updateEditorButtons() {
    const busy = ["rendering", "saving"].includes(state.phase);
    $("#undo-button").disabled = busy || state.commands.length === 0;
    $("#redo-button").disabled = busy || state.redoCommands.length === 0;
    $("#confirm-review-button").hidden = state.phase === "preview_ready";
    $("#confirm-review-button").disabled = busy || !state.current;
    $("#confirm-review-button").textContent = state.phase === "rendering"
      ? "正在生成…"
      : "生成临时预览";
    $("#continue-adjustment-button").hidden = state.phase !== "preview_ready";
    $("#save-adjustment-button").hidden = state.phase !== "preview_ready";
    $("#save-adjustment-button").disabled = state.phase === "saving";
    $("#editor-result-tab").disabled = !state.resultImage;
    $("#editor-mask-tab").classList.toggle("is-active", state.viewVariant === "mask");
    $("#editor-result-tab").classList.toggle("is-active", state.viewVariant === "result");
    $("#editor-mask-tab").setAttribute("aria-selected", String(state.viewVariant === "mask"));
    $("#editor-result-tab").setAttribute("aria-selected", String(state.viewVariant === "result"));
    $$(".tool-button[data-tool], #restore-button, #mask-margin, #brush-size").forEach((control) => {
      control.disabled = busy || state.viewVariant === "result";
    });
    $("#skip-review-button").disabled = busy;
  }

  function findPolygon(point) {
    for (let index = state.polygons.length - 1; index >= 0; index -= 1) {
      if (pointInPolygon(point, state.polygons[index].points)) return state.polygons[index];
    }
    return null;
  }

  function findCorner(point) {
    const radius = 13 / state.view.scale;
    for (let polygonIndex = state.polygons.length - 1; polygonIndex >= 0; polygonIndex -= 1) {
      const polygon = state.polygons[polygonIndex];
      for (let corner = 0; corner < 4; corner += 1) {
        if (Math.hypot(
          point[0] - polygon.points[corner][0],
          point[1] - polygon.points[corner][1]
        ) <= radius) return { polygon, corner };
      }
    }
    return null;
  }

  function replacePolygonPoints(identifier, points) {
    const polygon = state.polygons.find((value) => value.id === identifier);
    if (polygon) polygon.points = clonePoints(points);
  }

  function uuid() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return window.crypto.randomUUID();
    }
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (value) => {
      const random = Math.random() * 16 | 0;
      return (value === "x" ? random : (random & 3 | 8)).toString(16);
    });
  }

  function createPolygon(center) {
    const halfWidth = Math.max(30, state.current.width * .08);
    const halfHeight = Math.max(14, state.current.height * .035);
    return [
      clampPoint([center[0] - halfWidth * .92, center[1] - halfHeight]),
      clampPoint([center[0] + halfWidth, center[1] - halfHeight * .82]),
      clampPoint([center[0] + halfWidth * .92, center[1] + halfHeight]),
      clampPoint([center[0] - halfWidth, center[1] + halfHeight * .82])
    ];
  }

  function setTool(tool) {
    state.tool = tool;
    $$(".tool-button[data-tool]").forEach((button) => {
      const active = button.dataset.tool === tool;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
    $("#brush-control").hidden = !["brush_add", "brush_erase"].includes(tool);
    updateCanvasCursor();
  }

  function updateCanvasCursor() {
    const canvas = $("#review-canvas");
    if (state.spaceDown) canvas.style.cursor = "grab";
    else if (state.tool === "remove_detection") canvas.style.cursor = "not-allowed";
    else if (state.tool === "polygon") canvas.style.cursor = "default";
    else canvas.style.cursor = "crosshair";
  }

  function initCanvas() {
    const canvas = $("#review-canvas");
    canvas.addEventListener("pointerdown", (event) => {
      if (!state.current || state.viewVariant !== "mask" || state.phase !== "editing") return;
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
      if (state.tool === "add_polygon") {
        const points = createPolygon(point);
        if (isValidQuadrilateral(points)) {
          const identifier = uuid();
          commitCommand({ type: "add_polygon", id: identifier, points });
          state.selectedPolygonId = `manual:${identifier}`;
          setTool("polygon");
        }
        return;
      }
      if (state.tool === "remove_detection") {
        const polygon = findPolygon(point);
        if (polygon) commitCommand({
          type: "remove_detection",
          target_id: polygon.id
        });
        return;
      }
      if (state.tool === "polygon") {
        const corner = findCorner(point);
        const polygon = corner ? corner.polygon : findPolygon(point);
        if (!polygon) {
          state.selectedPolygonId = null;
          draw();
          return;
        }
        state.selectedPolygonId = polygon.id;
        state.pointer = {
          type: corner ? "corner" : "polygon",
          corner: corner ? corner.corner : -1,
          targetId: polygon.id,
          start: point,
          original: clonePoints(polygon.points),
          current: clonePoints(polygon.points)
        };
        draw();
        return;
      }
      state.pointer = { type: state.tool, points: [point] };
      state.previewCommand = {
        type: state.tool,
        points: [point],
        radius: state.brushSize
      };
    });
    canvas.addEventListener("pointermove", (event) => {
      if (!state.pointer) return;
      if (state.pointer.type === "pan") {
        state.view.x = state.pointer.viewX + event.clientX - state.pointer.x;
        state.view.y = state.pointer.viewY + event.clientY - state.pointer.y;
      } else if (["corner", "polygon"].includes(state.pointer.type)) {
        const point = sourcePoint(event);
        let points = clonePoints(state.pointer.original);
        if (state.pointer.type === "corner") {
          points[state.pointer.corner] = point;
        } else {
          const dx = point[0] - state.pointer.start[0];
          const dy = point[1] - state.pointer.start[1];
          const minX = Math.min(...points.map((value) => value[0]));
          const maxX = Math.max(...points.map((value) => value[0]));
          const minY = Math.min(...points.map((value) => value[1]));
          const maxY = Math.max(...points.map((value) => value[1]));
          const safeX = Math.max(-minX, Math.min(state.current.width - maxX, dx));
          const safeY = Math.max(-minY, Math.min(state.current.height - maxY, dy));
          points = points.map((value) => [value[0] + safeX, value[1] + safeY]);
        }
        if (isValidQuadrilateral(points)) {
          state.pointer.current = points;
          replacePolygonPoints(state.pointer.targetId, points);
        }
      } else {
        const point = sourcePoint(event);
        const points = state.previewCommand.points;
        const previous = points[points.length - 1];
        if (Math.hypot(point[0] - previous[0], point[1] - previous[1]) >
            2 / state.view.scale) points.push(point);
      }
      draw();
    });
    function finishPointer(cancelled) {
      if (!state.pointer) return;
      if (!cancelled && ["corner", "polygon"].includes(state.pointer.type)) {
        const changed = JSON.stringify(state.pointer.current) !==
          JSON.stringify(state.pointer.original);
        if (changed) commitCommand({
          type: "set_detection_polygon",
          target_id: state.pointer.targetId,
          points: state.pointer.current
        });
        else rebuildPolygons();
      } else if (
        !cancelled &&
        ["brush_add", "brush_erase"].includes(state.pointer.type) &&
        state.previewCommand
      ) {
        commitCommand(state.previewCommand);
      } else if (cancelled) {
        rebuildPolygons();
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

  function commandsForPreview() {
    return [
      ...state.commands.filter((command) => command.type !== "set_margin"),
      { type: "set_margin", value: state.marginRatio }
    ];
  }

  async function generatePreview() {
    if (!state.current) return;
    state.submittedCommands = commandsForPreview();
    try {
      const response = await PlateApp.bridge.call(
        "preview_adjustment",
        state.current.id,
        state.current.revision,
        state.submittedCommands
      );
      if (!response.accepted) {
        PlateApp.toast.show(response.message);
        state.phase = "editing";
        updateEditorButtons();
      }
    } catch (error) {
      state.phase = "editing";
      updateEditorButtons();
      PlateApp.toast.show(`无法生成临时预览：${error.message || error}`);
    }
  }

  async function savePreview() {
    if (!state.current || !state.previewToken) return;
    const response = await PlateApp.bridge.call(
      "save_adjustment",
      state.current.id,
      state.previewToken
    );
    if (!response.accepted) PlateApp.toast.show(response.message);
  }

  async function cancelAndReturn() {
    if (!state.current) return;
    if (!await confirmDiscard()) return;
    await PlateApp.bridge.call("cancel_adjustment", state.current.id).catch(() => {});
    state.dirty = false;
    resetEditorState();
    setMode("queue");
    await PlateApp.navigate("batch");
  }

  async function move(direction) {
    if (!state.current || state.mode !== "queue" || state.items.length < 2) return;
    const index = state.items.findIndex((item) => item.id === state.current.id);
    const next = (index + direction + state.items.length) % state.items.length;
    await load(state.items[next].id);
  }

  function removeCurrent(identifier) {
    const index = state.items.findIndex((item) => item.id === identifier);
    state.items = state.items.filter((item) => item.id !== identifier);
    resetEditorState();
    render();
    if (state.items.length) load(state.items[Math.min(index, state.items.length - 1)].id);
  }

  function showView(variant) {
    if (variant === "result" && !state.resultImage) return;
    state.viewVariant = variant;
    updateEditorButtons();
    draw();
  }

  function handleEvent(event) {
    const payload = event.payload || {};
    if (!state.current || payload.job_id && payload.job_id !== state.current.id) {
      if (event.name === "history_changed") refresh();
      return;
    }
    switch (event.name) {
      case "adjustment_preview_started":
        state.phase = "rendering";
        $("#review-risk-text").textContent = "正在生成本地临时结果，不会写入输出文件夹…";
        updateEditorButtons();
        break;
      case "adjustment_preview_ready": {
        const image = new Image();
        image.onload = () => {
          state.resultImage = image;
          state.previewToken = payload.preview_token;
          state.phase = "preview_ready";
          state.viewVariant = "result";
          state.dirty = true;
          $("#review-risk-text").textContent = "这是临时结果；满意后再保存为新文件";
          updateEditorButtons();
          draw();
        };
        image.onerror = () => {
          state.phase = "editing";
          updateEditorButtons();
          PlateApp.toast.show("临时结果预览无法显示，请重试。");
        };
        image.src = payload.image;
        break;
      }
      case "adjustment_preview_failed":
        state.phase = "editing";
        $("#review-risk-text").textContent = "临时结果生成失败，区域调整已经保留";
        updateEditorButtons();
        PlateApp.toast.show(`生成失败：${payload.message}`);
        break;
      case "adjustment_save_started":
        state.phase = "saving";
        $("#review-risk-text").textContent = "正在保存新结果…";
        updateEditorButtons();
        break;
      case "adjustment_saved":
        state.previewToken = null;
        state.dirty = false;
        PlateApp.toast.show(`已保存 ${payload.output_name}`);
        if (state.mode === "single") {
          resetEditorState();
          setMode("queue");
          PlateApp.navigate("batch");
        } else {
          removeCurrent(payload.job_id);
        }
        break;
      case "adjustment_save_failed":
        state.phase = "preview_ready";
        $("#review-risk-text").textContent = "保存失败，临时结果仍可再次保存";
        updateEditorButtons();
        PlateApp.toast.show(`保存失败：${payload.message}`);
        break;
      case "review_skipped":
        if (state.mode === "queue") removeCurrent(payload.job_id);
        break;
      case "history_changed":
        if (state.mode === "queue") refresh();
        break;
      default:
        break;
    }
  }

  function init() {
    $$(".tool-button[data-tool]").forEach((button) => {
      button.addEventListener("click", () => setTool(button.dataset.tool));
    });
    $("#brush-size").addEventListener("input", (event) => {
      state.brushSize = Number(event.target.value);
      $("#brush-size-value").textContent = state.brushSize;
    });
    $("#mask-opacity").addEventListener("input", (event) => {
      state.maskOpacity = Number(event.target.value) / 100;
      draw();
    });
    $("#mask-margin").addEventListener("input", (event) => {
      const percent = Number(event.target.value);
      state.marginRatio = percent / 100;
      $("#mask-margin-value").textContent = `${percent >= 0 ? "+" : ""}${percent}%`;
      draw();
    });
    $("#mask-margin").addEventListener("change", () => {
      commitCommand({ type: "set_margin", value: state.marginRatio });
    });
    $("#undo-button").addEventListener("click", () => {
      if (!state.commands.length) return;
      invalidatePreview();
      state.redoCommands.push(state.commands.pop());
      state.dirty = true;
      rebuildPolygons();
      updateEditorButtons();
      draw();
    });
    $("#redo-button").addEventListener("click", () => {
      if (!state.redoCommands.length) return;
      invalidatePreview();
      state.commands.push(state.redoCommands.pop());
      state.dirty = true;
      rebuildPolygons();
      updateEditorButtons();
      draw();
    });
    $("#restore-button").addEventListener("click", () => {
      invalidatePreview();
      state.redoCommands = [...state.commands].reverse();
      state.commands = [];
      state.dirty = true;
      rebuildPolygons();
      updateEditorButtons();
      draw();
    });
    $("#confirm-review-button").addEventListener("click", generatePreview);
    $("#continue-adjustment-button").addEventListener("click", () => {
      invalidatePreview();
      $("#review-risk-text").textContent = "继续拖动角点或调整边缘范围";
      updateEditorButtons();
      draw();
    });
    $("#save-adjustment-button").addEventListener("click", () => {
      savePreview().catch((error) =>
        PlateApp.toast.show(`无法保存：${error.message || error}`)
      );
    });
    $("#cancel-adjustment-button").addEventListener("click", cancelAndReturn);
    $("#editor-mask-tab").addEventListener("click", () => showView("mask"));
    $("#editor-result-tab").addEventListener("click", () => showView("result"));
    $("#skip-review-button").addEventListener("click", async () => {
      if (!state.current || state.mode !== "queue") return;
      if (!await confirmDiscard()) return;
      const accepted = await PlateApp.bridge.call("skip_review", state.current.id);
      if (!accepted) PlateApp.toast.show("未能跳过此图，请重试。");
    });
    $("#previous-review-button").addEventListener("click", () => move(-1));
    $("#next-review-button").addEventListener("click", () => move(1));
    initCanvas();
    setTool("polygon");
  }

  PlateApp.review = {
    activate,
    confirmDiscard,
    discardEdits,
    draw,
    expandedPolygon,
    handleEvent,
    init,
    isMeaningfulRectangle,
    isValidQuadrilateral,
    load,
    move,
    needsRefit,
    openSingle,
    pointInPolygon,
    refresh,
    state
  };
})();
