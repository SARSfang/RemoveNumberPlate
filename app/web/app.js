(() => {
  "use strict";

  const state = {
    running: false,
    paused: false,
    total: 0,
    counts: { completed: 0, review_required: 0, failed: 0 },
    rows: new Map(),
    reviewItems: [],
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
    state.counts = { completed: 0, review_required: 0, failed: 0 };
    state.rows.clear();
    state.reviewItems = [];
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
      state.reviewItems.push(payload);
      renderReview();
    }
  }

  function renderReview() {
    const list = $("#review-list");
    const empty = $("#review-empty");
    if (state.reviewItems.length === 0) {
      empty.hidden = false;
      list.hidden = true;
      return;
    }
    empty.hidden = true;
    list.hidden = false;
    list.innerHTML = "";
    state.reviewItems.forEach((item) => {
      const card = document.createElement("article");
      card.className = "review-item";
      const title = document.createElement("strong");
      title.textContent = item.name;
      const detail = document.createElement("span");
      detail.textContent = "检测存在风险，原图未被修改";
      card.append(title, detail);
      list.appendChild(card);
    });
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
        break;
    }
  }

  window.app = { receiveBackendEvent };

  window.addEventListener("pywebviewready", async () => {
    const bootstrap = await window.pywebview.api.bootstrap();
    $("#gpu-name").textContent = bootstrap.gpu;
    $("#runtime-name").textContent = bootstrap.runtime;
    $("#model-state").textContent = bootstrap.models_ready ? "已校验，可以处理" : "模型缺失或校验失败";
    $("#model-state").style.color = bootstrap.models_ready ? "var(--success)" : "var(--danger)";
    const counts = bootstrap.history_counts || {};
    $("#history-total").textContent = Object.values(counts).reduce((sum, value) => sum + value, 0);
    await window.pywebview.api.frontend_ready();
  });

  $$(".nav-item").forEach((button) => button.addEventListener("click", () => setPage(button.dataset.page)));
  $("#review-button").addEventListener("click", () => setPage("review"));
  $("#choose-files").addEventListener("click", async () => startBatch(await window.pywebview.api.choose_files()));
  $("#choose-folder").addEventListener("click", async () => startBatch(await window.pywebview.api.choose_folder()));
  $("#pause-button").addEventListener("click", async () => {
    if (state.paused) await window.pywebview.api.resume();
    else await window.pywebview.api.pause();
  });
  $("#cancel-button").addEventListener("click", () => window.pywebview.api.cancel());

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
