(function () {
  "use strict";
  const PlateApp = window.PlateApp = window.PlateApp || {};
  const $ = (selector) => document.querySelector(selector);
  const state = { jobs: [], selectedId: null };

  const LABELS = {
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

  function action(label, callback) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "output-link";
    button.textContent = label;
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      callback();
    });
    return button;
  }

  function visibleJobs() {
    const query = $("#history-search").value.trim().toLocaleLowerCase("zh-CN");
    const filter = $("#history-filter").value;
    return state.jobs.filter((job) => {
      const matchesQuery = !query || job.name.toLocaleLowerCase("zh-CN").includes(query);
      const matchesStatus = filter === "all" || job.status === filter;
      return matchesQuery && matchesStatus;
    });
  }

  function formatDate(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString("zh-CN");
  }

  function showDetail(job) {
    state.selectedId = job.id;
    const detail = $("#history-detail");
    detail.replaceChildren();
    const title = document.createElement("h2");
    title.textContent = job.name;
    const status = document.createElement("span");
    status.className = `status status-${job.status}`;
    status.textContent = LABELS[job.status] || job.status;
    const facts = document.createElement("dl");
    [
      ["更新时间", formatDate(job.updated_at)],
      ["处理耗时", job.elapsed == null ? "—" : `${Number(job.elapsed).toFixed(2)} 秒`],
      ["识别区域", `${Number(job.detection_count || 0)} 处`],
      ["风险", job.risks && job.risks.length ? `${job.risks.length} 项` : "无"],
      ["原图", job.source_available ? "可用" : "已移动"],
      ["输出", job.output_available ? "可用" : "未生成"]
    ].forEach(([term, value]) => {
      const row = document.createElement("div");
      const dt = document.createElement("dt");
      const dd = document.createElement("dd");
      dt.textContent = term;
      dd.textContent = value;
      row.append(dt, dd);
      facts.appendChild(row);
    });
    detail.append(title, status, facts);
    render();
  }

  async function openOutput(job) {
    if (!await PlateApp.bridge.call("open_job_output", job.id)) {
      PlateApp.toast.show("输出文件夹暂不可用。");
    }
  }

  async function queueReview(job) {
    const response = await PlateApp.bridge.call("queue_for_manual_review", job.id);
    PlateApp.toast.show(response.message);
    if (response.accepted) {
      await PlateApp.review.refresh();
      await refresh();
      PlateApp.navigate("review");
    }
  }

  async function retry(job) {
    const response = await PlateApp.bridge.call("retry_job", job.id);
    PlateApp.toast.show(response.message);
    if (response.accepted) PlateApp.navigate("batch");
  }

  function render() {
    const jobs = visibleJobs();
    const rows = $("#history-rows");
    rows.replaceChildren();
    $("#history-total").textContent = state.jobs.length;
    if (!jobs.length) {
      const row = document.createElement("tr");
      row.className = "empty-row";
      const cell = document.createElement("td");
      cell.colSpan = 4;
      cell.textContent = state.jobs.length
        ? "没有符合筛选条件的任务。"
        : "还没有本机任务记录。";
      row.appendChild(cell);
      rows.appendChild(row);
      return;
    }
    jobs.forEach((job) => {
      const row = document.createElement("tr");
      row.classList.toggle("is-selected", job.id === state.selectedId);
      row.tabIndex = 0;
      row.addEventListener("click", () => showDetail(job));
      row.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          showDetail(job);
        }
      });

      const name = document.createElement("td");
      name.textContent = job.name;
      name.title = job.error || job.name;
      const statusCell = document.createElement("td");
      const status = document.createElement("span");
      status.className = `status status-${job.status}`;
      status.textContent = LABELS[job.status] || job.status;
      statusCell.appendChild(status);
      const updated = document.createElement("td");
      updated.textContent = formatDate(job.updated_at);
      const actions = document.createElement("td");
      const wrap = document.createElement("div");
      wrap.className = "history-actions";
      if (job.output_available) wrap.appendChild(action("打开输出", () => openOutput(job)));
      if (job.status === "review_required") {
        wrap.appendChild(action("进入复核", () => {
          PlateApp.navigate("review");
          window.setTimeout(() => PlateApp.review.load(job.id), 0);
        }));
      }
      if (job.status === "no_plate") {
        wrap.appendChild(action("手动标记", () => queueReview(job)));
      }
      if (["queued", "failed", "cancelled"].includes(job.status)) {
        wrap.appendChild(action("重新处理", () => retry(job)));
      }
      actions.appendChild(wrap);
      row.append(name, statusCell, updated, actions);
      rows.appendChild(row);
    });
  }

  async function refresh() {
    if (!PlateApp.bridge.api() || !PlateApp.bridge.api().list_history) return;
    state.jobs = await PlateApp.bridge.call("list_history", 100);
    if (state.selectedId && !state.jobs.some((job) => job.id === state.selectedId)) {
      state.selectedId = null;
    }
    render();
  }

  function init() {
    $("#refresh-history-button").addEventListener("click", refresh);
    $("#history-search").addEventListener("input", render);
    $("#history-filter").addEventListener("change", render);
  }

  PlateApp.history = { init, refresh, render, state };
})();
