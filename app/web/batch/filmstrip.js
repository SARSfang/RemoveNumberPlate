(function () {
  "use strict";
  const PlateApp = window.PlateApp = window.PlateApp || {};
  const thumbnailCache = new PlateApp.state.LruCache(64);
  const ITEM_WIDTH = 136;
  const VIRTUALIZE_AT = 40;
  let renderFrame = null;

  const $ = (selector) => document.querySelector(selector);

  function label(status) {
    return {
      queued: "等待中",
      detecting: "检测中",
      inpainting: "修复中",
      writing: "写入中",
      completed: "完成",
      review_required: "待复核",
      no_plate: "未发现",
      failed: "失败",
      cancelled: "已取消"
    }[status] || status;
  }

  async function loadThumbnail(job, node) {
    const cached = thumbnailCache.get(job.job_id);
    if (cached) {
      node.style.backgroundImage = `url("${cached}")`;
      return;
    }
    try {
      const response = await PlateApp.bridge.call("get_job_thumbnail", job.job_id);
      if (!response || !response.available) return;
      thumbnailCache.set(job.job_id, response.image);
      if (node.isConnected) node.style.backgroundImage = `url("${response.image}")`;
    } catch (_error) {
      // A missing thumbnail never interrupts the batch.
    }
  }

  function createItem(job, selected) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "filmstrip-item";
    button.classList.toggle("is-selected", selected);
    button.style.left = `${(job.index - 1) * ITEM_WIDTH}px`;
    button.dataset.jobId = job.job_id;
    button.title = job.name;
    button.setAttribute("role", "option");
    button.setAttribute("aria-selected", String(selected));
    button.tabIndex = selected ? 0 : -1;

    const thumb = document.createElement("span");
    thumb.className = "filmstrip-thumb";
    const index = document.createElement("span");
    index.className = "filmstrip-index";
    index.textContent = String(job.index).padStart(2, "0");
    const status = document.createElement("span");
    status.className = `filmstrip-status status-${job.status}`;
    status.textContent = label(job.status);
    thumb.append(index, status);

    const name = document.createElement("span");
    name.className = "filmstrip-name";
    name.textContent = job.name;
    button.append(thumb, name);
    button.addEventListener("click", () => PlateApp.batch.selectJob(job.job_id, true));
    loadThumbnail(job, thumb);
    return button;
  }

  function visibleRange(jobs, filmstrip) {
    if (jobs.length < VIRTUALIZE_AT) return [0, jobs.length];
    const visibleCount = Math.ceil(filmstrip.clientWidth / ITEM_WIDTH);
    const firstVisible = Math.floor(filmstrip.scrollLeft / ITEM_WIDTH);
    return [
      Math.max(0, firstVisible - visibleCount),
      Math.min(jobs.length, firstVisible + visibleCount * 2)
    ];
  }

  function render() {
    renderFrame = null;
    const filmstrip = $("#filmstrip");
    if (!filmstrip || !PlateApp.store) return;
    const state = PlateApp.store.get();
    const [start, end] = visibleRange(state.jobs, filmstrip);
    const focusedId = document.activeElement && document.activeElement.dataset
      ? document.activeElement.dataset.jobId
      : null;
    const track = document.createElement("div");
    track.className = "filmstrip-track";
    track.style.width = `${Math.max(state.jobs.length * ITEM_WIDTH, filmstrip.clientWidth)}px`;
    state.jobs.slice(start, end).forEach((job) => {
      track.appendChild(createItem(job, job.job_id === state.selectedId));
    });
    filmstrip.replaceChildren(track);
    if (focusedId) {
      const target = track.querySelector(`[data-job-id="${CSS.escape(focusedId)}"]`);
      if (target) target.focus({ preventScroll: true });
    }
  }

  function scheduleRender() {
    if (renderFrame !== null) return;
    renderFrame = window.requestAnimationFrame(render);
  }

  function ensureVisible(identifier) {
    const state = PlateApp.store.get();
    const index = state.jobs.findIndex((job) => job.job_id === identifier);
    const filmstrip = $("#filmstrip");
    if (index < 0 || !filmstrip) return;
    const left = index * ITEM_WIDTH;
    const right = left + ITEM_WIDTH;
    if (left < filmstrip.scrollLeft) {
      filmstrip.scrollTo({ left, behavior: "smooth" });
    } else if (right > filmstrip.scrollLeft + filmstrip.clientWidth) {
      filmstrip.scrollTo({
        left: right - filmstrip.clientWidth,
        behavior: "smooth"
      });
    }
  }

  function invalidate(identifier) {
    thumbnailCache.values.delete(identifier);
  }

  function move(delta) {
    const state = PlateApp.store.get();
    if (!state.jobs.length) return;
    const current = state.jobs.findIndex((job) => job.job_id === state.selectedId);
    const next = Math.max(0, Math.min(
      state.jobs.length - 1,
      current < 0 ? 0 : current + delta
    ));
    PlateApp.batch.selectJob(state.jobs[next].job_id, true);
  }

  function edge(position) {
    const state = PlateApp.store.get();
    if (!state.jobs.length) return;
    const job = position === "start" ? state.jobs[0] : state.jobs[state.jobs.length - 1];
    PlateApp.batch.selectJob(job.job_id, true);
  }

  function init() {
    const filmstrip = $("#filmstrip");
    filmstrip.addEventListener("scroll", scheduleRender, { passive: true });
    $("#filmstrip-previous").addEventListener("click", () => {
      filmstrip.scrollBy({ left: -filmstrip.clientWidth * .8, behavior: "smooth" });
    });
    $("#filmstrip-next").addEventListener("click", () => {
      filmstrip.scrollBy({ left: filmstrip.clientWidth * .8, behavior: "smooth" });
    });
    window.addEventListener("resize", scheduleRender);
    PlateApp.store.subscribe((_state, event) => {
      if (
        event.name === "batch_items_ready" ||
        event.name === "item_started" ||
        event.name === "item_finished" ||
        event.name === "job_selected" ||
        event.name === "follow_restored"
      ) {
        scheduleRender();
      }
    });
  }

  PlateApp.filmstrip = {
    VIRTUALIZE_AT,
    edge,
    ensureVisible,
    init,
    invalidate,
    move,
    render,
    thumbnailCache
  };
})();
