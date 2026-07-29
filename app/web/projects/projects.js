(function () {
  "use strict";
  const PlateApp = window.PlateApp = window.PlateApp || {};
  const $ = (selector) => document.querySelector(selector);

  // Project list and current project id come from bootstrap(); the dialog
  // mirrors this state locally so the user can iterate without re-fetching
  // for every change.
  const state = {
    projects: [],
    currentProjectId: null,
    editingId: null,
    isDialogOpen: false
  };

  const PRESET_LABELS = {
    balanced: "均衡",
    speed: "速度优先",
    quality: "精细处理"
  };

  const OUTPUT_MODE_LABELS = {
    beside_source: "原片旁",
    project_subfolder: "项目子文件夹",
    fixed_directory: "固定目录"
  };

  function formatDate(value) {
    if (!value) return "—";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString("zh-CN");
  }

  function buildProjectNameMap() {
    const map = new Map();
    state.projects.forEach((project) => {
      map.set(project.id, project.name);
    });
    return map;
  }

  function projectById(id) {
    return state.projects.find((project) => project.id === id) || null;
  }

  function renderProjectSelector() {
    const selector = $("#project-selector");
    const select = $("#current-project");
    if (!selector || !select) return;
    selector.hidden = state.projects.length === 0;
    if (state.projects.length === 0) return;
    select.replaceChildren();
    const noneOption = document.createElement("option");
    noneOption.value = "";
    noneOption.textContent = "无项目";
    select.appendChild(noneOption);
    state.projects.forEach((project) => {
      const option = document.createElement("option");
      option.value = project.id;
      option.textContent = project.name;
      select.appendChild(option);
    });
    // If the saved current project no longer exists (deleted by another
    // session or via the management dialog), clear the selector — the
    // backend will follow up with set_current_project(None).
    if (state.currentProjectId && !projectById(state.currentProjectId)) {
      state.currentProjectId = null;
    }
    select.value = state.currentProjectId || "";
  }

  function renderProjectFilter() {
    const filter = $("#history-project-filter");
    if (!filter) return;
    const previous = filter.value;
    filter.replaceChildren();
    const allOption = document.createElement("option");
    allOption.value = "";
    allOption.textContent = "全部项目";
    filter.appendChild(allOption);
    state.projects.forEach((project) => {
      const option = document.createElement("option");
      option.value = project.id;
      option.textContent = project.name;
      filter.appendChild(option);
    });
    if (previous && projectById(previous)) {
      filter.value = previous;
    }
  }

  function renderProjectsList() {
    const list = $("#projects-list");
    if (!list) return;
    list.replaceChildren();
    if (!state.projects.length) {
      const empty = document.createElement("p");
      empty.className = "projects-empty";
      empty.textContent = "还没有项目。点击“新建项目”创建一个。";
      list.appendChild(empty);
      return;
    }
    state.projects.forEach((project) => {
      const row = document.createElement("div");
      row.className = "project-row";
      if (state.currentProjectId === project.id) {
        row.classList.add("is-current");
      }
      const info = document.createElement("div");
      info.className = "project-row-info";
      const name = document.createElement("span");
      name.className = "project-row-name";
      name.textContent = project.name;
      name.title = project.name;
      const meta = document.createElement("span");
      meta.className = "project-row-meta";
      const presetLabel = PRESET_LABELS[project.preset] || project.preset;
      const marginPercent = Number(project.mask_margin_percent ?? 8);
      const outputLabel =
        OUTPUT_MODE_LABELS[project.output_directory_rule?.mode] || "原片旁";
      const lastUsed = project.last_used_at
        ? `最近使用：${formatDate(project.last_used_at)}`
        : "尚未使用";
      meta.textContent = `${presetLabel} · 边缘 ${marginPercent >= 0 ? "+" : ""}${marginPercent}% · 输出：${outputLabel} · ${lastUsed}`;
      info.append(name, meta);
      const actions = document.createElement("div");
      actions.className = "project-row-actions";
      const editButton = document.createElement("button");
      editButton.type = "button";
      editButton.textContent = "编辑";
      editButton.addEventListener("click", () => openEditForm(project.id));
      const deleteButton = document.createElement("button");
      deleteButton.type = "button";
      deleteButton.className = "project-delete";
      deleteButton.textContent = "删除";
      deleteButton.addEventListener("click", () => deleteProject(project.id));
      actions.append(editButton, deleteButton);
      row.append(info, actions);
      list.appendChild(row);
    });
  }

  function resetForm() {
    state.editingId = null;
    $("#project-form").hidden = true;
    $("#project-form-title").textContent = "新建项目";
    $("#project-name").value = "";
    $("#project-preset").value = "balanced";
    $("#project-mask-margin").value = "8";
    $("#project-output-mode").value = "beside_source";
    $("#project-subfolder-name").value = "";
    $("#project-fixed-directory").value = "";
    toggleOutputFields();
    $("#add-project-button").hidden = false;
    $("#save-project-button").hidden = true;
    $("#save-project-button").textContent = "保存项目";
    $("#cancel-project-button").hidden = true;
  }

  function openCreateForm() {
    resetForm();
    $("#project-form").hidden = false;
    $("#project-form-title").textContent = "新建项目";
    $("#save-project-button").hidden = false;
    $("#save-project-button").textContent = "创建项目";
    $("#add-project-button").hidden = true;
    $("#cancel-project-button").hidden = false;
    $("#project-name").focus();
  }

  function openEditForm(projectId) {
    const project = projectById(projectId);
    if (!project) return;
    state.editingId = projectId;
    $("#project-form").hidden = false;
    $("#project-form-title").textContent = "编辑项目";
    $("#project-name").value = project.name;
    $("#project-preset").value = project.preset || "balanced";
    $("#project-mask-margin").value = String(project.mask_margin_percent ?? 8);
    const rule = project.output_directory_rule || {};
    $("#project-output-mode").value = rule.mode || "beside_source";
    $("#project-subfolder-name").value = rule.subfolder_name || "";
    $("#project-fixed-directory").value = rule.fixed_directory || "";
    toggleOutputFields();
    $("#add-project-button").hidden = true;
    $("#save-project-button").hidden = false;
    $("#save-project-button").textContent = "保存修改";
    $("#cancel-project-button").hidden = false;
    $("#project-name").focus();
  }

  function toggleOutputFields() {
    const mode = $("#project-output-mode").value;
    const isSubfolder = mode === "project_subfolder";
    const isFixed = mode === "fixed_directory";
    $("#project-subfolder-label").hidden = !isSubfolder;
    $("#project-subfolder-name").hidden = !isSubfolder;
    $("#project-fixed-label").hidden = !isFixed;
    $("#project-fixed-directory").hidden = !isFixed;
  }

  function collectFormPayload() {
    const mode = $("#project-output-mode").value;
    const rule = { mode };
    if (mode === "project_subfolder") {
      rule.subfolder_name = $("#project-subfolder-name").value.trim();
    }
    if (mode === "fixed_directory") {
      rule.fixed_directory = $("#project-fixed-directory").value.trim();
    }
    return {
      name: $("#project-name").value.trim(),
      preset: $("#project-preset").value,
      mask_margin_ratio: Number($("#project-mask-margin").value || 0) / 100,
      output_directory_rule: rule
    };
  }

  async function saveProject() {
    const payload = collectFormPayload();
    if (!payload.name) {
      PlateApp.toast.show("项目名称不能为空。");
      $("#project-name").focus();
      return;
    }
    const saveButton = $("#save-project-button");
    saveButton.disabled = true;
    try {
      let response;
      if (state.editingId) {
        response = await PlateApp.bridge.call(
          "update_project",
          state.editingId,
          payload
        );
      } else {
        response = await PlateApp.bridge.call(
          "create_project",
          payload.name,
          {
            preset: payload.preset,
            mask_margin_ratio: payload.mask_margin_ratio,
            output_directory_rule: payload.output_directory_rule
          }
        );
      }
      if (!response.accepted) {
        PlateApp.toast.show(response.message || "保存项目失败。");
        return;
      }
      PlateApp.toast.show(state.editingId ? "项目已更新。" : "项目已创建。");
      await refreshProjects();
      resetForm();
    } catch (error) {
      PlateApp.toast.show(`无法保存项目：${error.message || error}`);
    } finally {
      saveButton.disabled = false;
    }
  }

  async function deleteProject(projectId) {
    const project = projectById(projectId);
    if (!project) return;
    const accepted = await PlateApp.dialog.confirm({
      title: "删除项目？",
      description: `将删除“${project.name}”，关联任务的所属关系会清空但记录保留。`,
      confirmLabel: "删除"
    });
    if (!accepted) return;
    try {
      const response = await PlateApp.bridge.call("delete_project", projectId);
      if (!response.accepted) {
        PlateApp.toast.show(response.message || "删除项目失败。");
        return;
      }
      PlateApp.toast.show("项目已删除。");
      if (state.editingId === projectId) {
        resetForm();
      }
      await refreshProjects();
    } catch (error) {
      PlateApp.toast.show(`无法删除项目：${error.message || error}`);
    }
  }

  async function setCurrentProject(projectId) {
    const target = projectId || null;
    try {
      const response = await PlateApp.bridge.call("set_current_project", target);
      if (!response.accepted) {
        PlateApp.toast.show(response.message || "切换项目失败。");
        // Restore previous selection.
        $("#current-project").value = state.currentProjectId || "";
        return;
      }
      state.currentProjectId = target;
      renderProjectsList();
    } catch (error) {
      PlateApp.toast.show(`无法切换项目：${error.message || error}`);
      $("#current-project").value = state.currentProjectId || "";
    }
  }

  async function refreshProjects() {
    try {
      const response = await PlateApp.bridge.call("list_projects");
      state.projects = response.projects || [];
      renderProjectSelector();
      renderProjectFilter();
      renderProjectsList();
    } catch (error) {
      PlateApp.toast.show(`无法加载项目列表：${error.message || error}`);
    }
  }

  function openDialog() {
    state.isDialogOpen = true;
    $("#projects-dialog").hidden = false;
    resetForm();
    renderProjectsList();
    window.setTimeout(() => $("#projects-dialog-close").focus(), 0);
  }

  function closeDialog() {
    state.isDialogOpen = false;
    $("#projects-dialog").hidden = true;
    resetForm();
  }

  function hydrate(bootstrap) {
    state.projects = Array.isArray(bootstrap.projects) ? bootstrap.projects : [];
    state.currentProjectId = bootstrap.current_project_id || null;
    renderProjectSelector();
    renderProjectFilter();
    renderProjectsList();
  }

  function handleEvent(event) {
    if (event.name === "projects_changed") {
      refreshProjects();
    }
  }

  function getProjects() {
    return state.projects.slice();
  }

  function getCurrentProjectId() {
    return state.currentProjectId;
  }

  function init() {
    const selector = $("#current-project");
    if (selector) {
      selector.addEventListener("change", (event) => {
        setCurrentProject(event.currentTarget.value || null);
      });
    }
    const manageButton = $("#manage-projects-button");
    if (manageButton) {
      manageButton.addEventListener("click", openDialog);
    }
    const closeButton = $("#projects-dialog-close");
    if (closeButton) {
      closeButton.addEventListener("click", closeDialog);
    }
    const addButton = $("#add-project-button");
    if (addButton) {
      addButton.addEventListener("click", openCreateForm);
    }
    const saveButton = $("#save-project-button");
    if (saveButton) {
      saveButton.addEventListener("click", saveProject);
    }
    const cancelButton = $("#cancel-project-button");
    if (cancelButton) {
      cancelButton.addEventListener("click", resetForm);
    }
    const outputMode = $("#project-output-mode");
    if (outputMode) {
      outputMode.addEventListener("change", toggleOutputFields);
    }
    const backdrop = $("#projects-dialog");
    if (backdrop) {
      backdrop.addEventListener("mousedown", (event) => {
        if (event.target === backdrop) closeDialog();
      });
      backdrop.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
          event.preventDefault();
          closeDialog();
        }
      });
    }
  }

  PlateApp.projects = {
    init,
    hydrate,
    handleEvent,
    refreshProjects,
    getProjects,
    getCurrentProjectId,
    closeDialog,
    buildProjectNameMap
  };
})();
