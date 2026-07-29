(function () {
  "use strict";
  const PlateApp = window.PlateApp = window.PlateApp || {};
  const $ = (selector) => document.querySelector(selector);
  const state = { jobs: [], total: 0, selectedId: null, lastQuery: null };
  let refreshSerial = 0;
  let searchDebounce = null;

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

  function formatDate(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString("zh-CN");
  }

  function buildProjectNameMap() {
    if (!PlateApp.projects || typeof PlateApp.projects.getProjects !== "function") {
      return new Map();
    }
    const map = new Map();
    PlateApp.projects.getProjects().forEach((project) => {
      map.set(project.id, project.name);
    });
    return map;
  }

  function collectQuery() {
    const nameContains = $("#history-search").value.trim();
    const statusValue = $("#history-filter").value;
    const dateFrom = $("#history-date-from").value;
    const dateTo = $("#history-date-to").value;
    const projectId = $("#history-project-filter").value;
    const query = {
      name_contains: nameContains,
      date_from: dateFrom || null,
      date_to: dateTo || null
    };
    if (statusValue !== "all") {
      query.statuses = [statusValue];
    }
    if (projectId) {
      query.project_ids = [projectId];
      // Keep include_no_project default (True) so users can still see jobs
      // that lost their project alongside the filtered one — but only when
      // no specific project is selected. When a project is selected, hide
      // no-project rows so the user sees exactly that project's jobs.
      query.include_no_project = false;
    }
    return query;
  }

  function closeDetail() {
    const detail = $("#history-detail");
    detail.classList.remove("is-open");
    const selected = $("#history-rows tr.is-selected");
    if (selected) selected.focus();
  }

  function renderDetail(job) {
    const detail = $("#history-detail");
    detail.replaceChildren();
    if (!job) {
      detail.classList.remove("is-open");
      const empty = document.createElement("div");
      empty.className = "empty-detail";
      const icon = document.createElement("img");
      icon.src = "assets/icons/panel-right.svg";
      icon.alt = "";
      const title = document.createElement("strong");
      title.textContent = state.jobs.length
        ? "选择一条任务"
        : "暂无任务记录";
      const description = document.createElement("span");
      description.textContent = state.jobs.length
        ? "在这里查看状态、风险和输出。"
        : "完成处理后，记录会安全地保存在本机。";
      empty.append(icon, title, description);
      detail.appendChild(empty);
      return;
    }
    const closeButton = document.createElement("button");
    closeButton.type = "button";
    closeButton.className = "icon-button history-detail-close";
    closeButton.setAttribute("aria-label", "关闭任务详情");
    closeButton.title = "关闭任务详情";
    const closeIcon = document.createElement("img");
    closeIcon.src = "assets/icons/circle-x.svg";
    closeIcon.alt = "";
    closeButton.appendChild(closeIcon);
    closeButton.addEventListener("click", closeDetail);
    const title = document.createElement("h2");
    title.textContent = job.name;
    const status = document.createElement("span");
    status.className = `status status-${job.status}`;
    status.textContent = LABELS[job.status] || job.status;
    const facts = document.createElement("dl");
    const projectNameMap = buildProjectNameMap();
    const projectName = job.project_id
      ? (projectNameMap.get(job.project_id) || "已删除项目")
      : "无";
    [
      ["更新时间", formatDate(job.updated_at)],
      ["处理耗时", job.elapsed == null ? "—" : `${Number(job.elapsed).toFixed(2)} 秒`],
      ["识别区域", `${Number(job.detection_count || 0)} 处`],
      ["风险", job.risks && job.risks.length ? `${job.risks.length} 项` : "无"],
      ["原图", job.source_available ? "可用" : "已移动"],
      ["输出", job.output_available ? "可用" : "未生成"],
      ["项目", projectName]
    ].forEach(([term, value]) => {
      const row = document.createElement("div");
      const dt = document.createElement("dt");
      const dd = document.createElement("dd");
      dt.textContent = term;
      dd.textContent = value;
      row.append(dt, dd);
      facts.appendChild(row);
    });
    detail.append(closeButton, title, status, facts);
  }

  function showDetail(job) {
    state.selectedId = job.id;
    render();
    if (window.matchMedia("(max-width: 800px)").matches) {
      $("#history-detail").classList.add("is-open");
    }
  }

  async function openOutput(job) {
    try {
      if (await PlateApp.bridge.call("open_job_output", job.id)) return;
      PlateApp.toast.show("输出文件夹暂不可用。");
    } catch (error) {
      PlateApp.toast.show(`无法打开输出文件夹：${error.message || error}`);
    }
  }

  async function queueReview(job) {
    try {
      const response = await PlateApp.bridge.call("queue_for_manual_review", job.id);
      PlateApp.toast.show(response.message);
      if (response.accepted) {
        await PlateApp.review.refresh();
        await refresh();
        PlateApp.navigate("review");
      }
    } catch (error) {
      PlateApp.toast.show(`无法加入待复核：${error.message || error}`);
    }
  }

  async function retry(job) {
    try {
      const response = await PlateApp.bridge.call("retry_job", job.id);
      PlateApp.toast.show(response.message);
      if (response.accepted) PlateApp.navigate("batch");
    } catch (error) {
      PlateApp.toast.show(`无法重新处理：${error.message || error}`);
    }
  }

  function render() {
    const jobs = state.jobs;
    if (state.selectedId && !jobs.some((job) => job.id === state.selectedId)) {
      state.selectedId = null;
    }
    if (!state.selectedId && jobs.length) {
      state.selectedId = jobs[0].id;
    }
    const rows = $("#history-rows");
    rows.replaceChildren();
    $("#history-total").textContent = String(state.total ?? jobs.length);
    if (!jobs.length) {
      const row = document.createElement("tr");
      row.className = "empty-row";
      const cell = document.createElement("td");
      cell.colSpan = 4;
      cell.textContent = state.total
        ? "没有符合筛选条件的任务。"
        : "还没有本机任务记录。";
      row.appendChild(cell);
      rows.appendChild(row);
      renderDetail(null);
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
    renderDetail(state.jobs.find((job) => job.id === state.selectedId) || null);
  }

  async function refresh() {
    // Spec v0.3.0 §4: prefer search_history when available so the backend
    // can apply date/project filters that list_history ignores.
    if (!PlateApp.bridge.api()) return;
    const hasSearch = typeof PlateApp.bridge.api().search_history === "function";
    if (!hasSearch && typeof PlateApp.bridge.api().list_history !== "function") {
      return;
    }
    const serial = ++refreshSerial;
    const workspace = $("#history-workspace");
    const refreshButton = $("#refresh-history-button");
    workspace.setAttribute("aria-busy", "true");
    refreshButton.disabled = true;
    try {
      const query = collectQuery();
      state.lastQuery = query;
      const response = hasSearch
        ? await PlateApp.bridge.call("search_history", query)
        : { jobs: await PlateApp.bridge.call("list_history", 100), total: 0 };
      if (serial !== refreshSerial) return;
      state.jobs = response.jobs || [];
      state.total = hasSearch ? (response.total ?? state.jobs.length) : state.jobs.length;
      if (state.selectedId && !state.jobs.some((job) => job.id === state.selectedId)) {
        state.selectedId = null;
      }
      if (!state.selectedId && state.jobs.length) {
        state.selectedId = state.jobs[0].id;
      }
      render();
    } catch (error) {
      if (serial !== refreshSerial) return;
      PlateApp.toast.show(`无法刷新任务历史：${error.message || error}`);
    } finally {
      if (serial === refreshSerial) {
        workspace.setAttribute("aria-busy", "false");
        refreshButton.disabled = false;
      }
    }
  }

  function scheduleSearch() {
    if (searchDebounce) clearTimeout(searchDebounce);
    searchDebounce = setTimeout(() => {
      searchDebounce = null;
      refresh();
    }, 300);
  }

  function init() {
    $("#refresh-history-button").addEventListener("click", refresh);
    $("#history-search").addEventListener("input", scheduleSearch);
    $("#history-filter").addEventListener("change", refresh);
    $("#history-date-from").addEventListener("change", refresh);
    $("#history-date-to").addEventListener("change", refresh);
    $("#history-project-filter").addEventListener("change", refresh);
    document.addEventListener("keydown", (event) => {
      if (
        event.key === "Escape" &&
        $("#history-detail").classList.contains("is-open")
      ) {
        event.preventDefault();
        closeDetail();
      }
    });
  }

  PlateApp.history = { init, refresh, render, state };
})();
