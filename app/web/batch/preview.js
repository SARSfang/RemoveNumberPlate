(function () {
  "use strict";
  const PlateApp = window.PlateApp = window.PlateApp || {};
  const cache = new PlateApp.state.LruCache(6);
  let requestSerial = 0;
  let current = null;
  let scale = 1;
  let panX = 0;
  let panY = 0;
  let pointer = null;
  let skeletonTimer = null;

  const $ = (selector) => document.querySelector(selector);

  function selectedJob() {
    const state = PlateApp.store && PlateApp.store.get();
    return state && state.jobs.find((job) => job.job_id === state.selectedId);
  }

  function actualVariant(variant) {
    document.querySelectorAll(".preview-tab").forEach((tab) => {
      const active = tab.dataset.variant === variant;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", String(active));
      tab.tabIndex = active ? 0 : -1;
    });
  }

  function updateTransform() {
    const image = $("#preview-image");
    if (!image || image.hidden) return;
    image.style.transform = `translate(-50%, -50%) translate(${panX}px, ${panY}px) scale(${scale})`;
    $("#preview-fit").textContent = Math.abs(scale - fitScale()) < .02
      ? "适应"
      : `${Math.round(scale * 100)}%`;
  }

  function fitScale() {
    const viewport = $("#preview-viewport");
    const image = $("#preview-image");
    if (!viewport || !image || !image.naturalWidth || !image.naturalHeight) return 1;
    return Math.min(
      viewport.clientWidth / image.naturalWidth,
      viewport.clientHeight / image.naturalHeight
    ) * .97;
  }

  function fit() {
    scale = fitScale();
    panX = 0;
    panY = 0;
    updateTransform();
  }

  function zoomBy(factor) {
    scale = Math.max(.08, Math.min(8, scale * factor));
    updateTransform();
  }

  function setLoading(loading) {
    window.clearTimeout(skeletonTimer);
    const skeleton = $("#preview-skeleton");
    if (!skeleton) return;
    skeleton.hidden = true;
    if (loading) {
      skeletonTimer = window.setTimeout(() => {
        skeleton.hidden = false;
      }, 300);
    }
  }

  function setUnavailable(message) {
    setLoading(false);
    $("#preview-image").hidden = true;
    $("#preview-placeholder").hidden = true;
    $("#preview-error").hidden = false;
    $("#preview-error-message").textContent = message || "照片处理不会受到影响。";
    $("#inspector-dimensions").textContent = "—";
  }

  function loadResponse(response) {
    current = response;
    setLoading(false);
    if (!response || !response.available) {
      setUnavailable(response && response.message);
      return;
    }
    $("#preview-error").hidden = true;
    $("#preview-placeholder").hidden = true;
    const image = $("#preview-image");
    image.onload = () => {
      image.hidden = false;
      fit();
    };
    image.onerror = () => setUnavailable("预览数据无法显示，请重试。");
    image.src = response.image;
    image.alt = `${$("#preview-file-name").textContent} · ${
      response.variant === "result" ? "处理结果" : "原图"
    }`;
    $("#inspector-dimensions").textContent = response.width && response.height
      ? `${response.width} × ${response.height}`
      : "—";
    actualVariant(response.variant);
  }

  async function fetchPreview(identifier, variant) {
    const key = `${identifier}:${variant}`;
    const cached = cache.get(key);
    if (cached) return cached;
    const response = await PlateApp.bridge.call("get_job_preview", identifier, variant);
    if (response && response.available) cache.set(key, response);
    return response;
  }

  async function show(job, options) {
    if (!job) {
      current = null;
      $("#preview-image").hidden = true;
      $("#preview-error").hidden = true;
      $("#preview-placeholder").hidden = false;
      return;
    }
    const serial = ++requestSerial;
    const preferred = options && options.variant
      ? options.variant
      : PlateApp.store.get().preferredVariant;
    setLoading(true);
    $("#preview-error").hidden = true;
    try {
      let response = await fetchPreview(job.job_id, preferred);
      if (
        preferred === "result" &&
        response &&
        !response.available &&
        ["output_not_ready", "output_missing"].includes(response.reason)
      ) {
        response = await fetchPreview(job.job_id, "original");
      }
      if (serial !== requestSerial) return;
      loadResponse(response);
    } catch (error) {
      if (serial !== requestSerial) return;
      setUnavailable(error.message || String(error));
    }
  }

  function invalidate(identifier, variant) {
    if (!identifier) return;
    if (variant) {
      cache.values.delete(`${identifier}:${variant}`);
    } else {
      cache.values.delete(`${identifier}:original`);
      cache.values.delete(`${identifier}:result`);
    }
  }

  function refresh() {
    const job = selectedJob();
    if (job) show(job);
  }

  function init() {
    const viewport = $("#preview-viewport");
    $("#preview-zoom-out").addEventListener("click", () => zoomBy(.86));
    $("#preview-zoom-in").addEventListener("click", () => zoomBy(1.16));
    $("#preview-fit").addEventListener("click", fit);
    $("#preview-retry-button").addEventListener("click", refresh);
    document.querySelectorAll(".preview-tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        PlateApp.store.patch(
          { preferredVariant: tab.dataset.variant },
          "preview_variant_changed"
        );
        const job = selectedJob();
        if (job) show(job, { variant: tab.dataset.variant });
      });
      tab.addEventListener("keydown", (event) => {
        if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
        event.preventDefault();
        const target = event.key === "ArrowLeft"
          ? $("#preview-tab-original")
          : $("#preview-tab-result");
        target.focus();
        target.click();
      });
    });
    viewport.addEventListener("wheel", (event) => {
      if ($("#preview-image").hidden) return;
      event.preventDefault();
      zoomBy(event.deltaY < 0 ? 1.12 : .89);
    }, { passive: false });
    viewport.addEventListener("pointerdown", (event) => {
      if ($("#preview-image").hidden) return;
      pointer = {
        id: event.pointerId,
        startX: event.clientX,
        startY: event.clientY,
        panX,
        panY
      };
      viewport.setPointerCapture(event.pointerId);
      viewport.classList.add("is-panning");
    });
    viewport.addEventListener("pointermove", (event) => {
      if (!pointer || pointer.id !== event.pointerId) return;
      panX = pointer.panX + event.clientX - pointer.startX;
      panY = pointer.panY + event.clientY - pointer.startY;
      updateTransform();
    });
    const release = () => {
      pointer = null;
      viewport.classList.remove("is-panning");
    };
    viewport.addEventListener("pointerup", release);
    viewport.addEventListener("pointercancel", release);
    window.addEventListener("resize", () => {
      if (current && current.available) fit();
    });
  }

  PlateApp.preview = {
    cache,
    fit,
    init,
    invalidate,
    refresh,
    show,
    zoomBy
  };
})();
