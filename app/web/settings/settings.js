(function () {
  "use strict";
  const PlateApp = window.PlateApp = window.PlateApp || {};
  const $ = (selector) => document.querySelector(selector);

  let namingPreviewTimer = null;
  const NAMING_SAMPLE = "DSC_0123.jpg";

  async function savePreset(event) {
    const select = event.currentTarget;
    const previous = select.dataset.savedValue || "balanced";
    select.disabled = true;
    try {
      const response = await PlateApp.bridge.call("set_preset", select.value);
      PlateApp.toast.show(response.message);
      if (response.accepted) {
        select.dataset.savedValue = select.value;
      } else {
        select.value = previous;
      }
    } catch (error) {
      select.value = previous;
      PlateApp.toast.show(`无法保存处理预设：${error.message || error}`);
    } finally {
      select.disabled = false;
    }
  }

  function renderMaskMargin(value) {
    const percent = Math.max(-30, Math.min(100, Math.round(Number(value))));
    const safePercent = Number.isFinite(percent) ? percent : 35;
    $("#default-mask-margin").value = String(safePercent);
    $("#default-mask-margin").setAttribute(
      "aria-valuetext",
      `${safePercent >= 0 ? "+" : ""}${safePercent}%`
    );
    $("#default-mask-margin-number").value = String(safePercent);
    $("#default-mask-margin-value").textContent =
      `${safePercent >= 0 ? "+" : ""}${safePercent}%`;
    $("#default-mask-margin-warning").hidden = safePercent <= 60;
    return safePercent;
  }

  async function saveMaskMargin(value) {
    const range = $("#default-mask-margin");
    const number = $("#default-mask-margin-number");
    const previous = Number(range.dataset.savedValue || 35);
    const percent = renderMaskMargin(value);
    range.disabled = true;
    number.disabled = true;
    try {
      const response = await PlateApp.bridge.call("set_mask_margin", percent);
      PlateApp.toast.show(response.message);
      if (response.accepted) {
        range.dataset.savedValue = String(percent);
        number.dataset.savedValue = String(percent);
      } else {
        renderMaskMargin(previous);
      }
    } catch (error) {
      renderMaskMargin(previous);
      PlateApp.toast.show(`无法保存默认边缘扩展：${error.message || error}`);
    } finally {
      range.disabled = false;
      number.disabled = false;
    }
  }

  function hydrate(bootstrap) {
    $("#gpu-name").textContent = bootstrap.gpu;
    $("#runtime-name").textContent = bootstrap.runtime;
    $("#model-state").textContent = bootstrap.models_ready
      ? "已校验，可以处理"
      : "模型缺失或校验失败";
    $("#model-state").style.color = bootstrap.models_ready
      ? "var(--success)"
      : "var(--danger)";
    $("#model-state").title = bootstrap.model_issue || "";
    $("#webview2-version").textContent = bootstrap.webview2_version;
    $("#preset").value = bootstrap.preset || "balanced";
    $("#preset").dataset.savedValue = $("#preset").value;
    const marginPercent = renderMaskMargin(bootstrap.mask_margin_percent ?? 35);
    $("#default-mask-margin").dataset.savedValue = String(marginPercent);
    $("#default-mask-margin-number").dataset.savedValue = String(marginPercent);
    renderWatchFolders(bootstrap.watch_folders || []);
    hydratePostProcess(bootstrap.post_process_config || {});
  }

  function hydratePostProcess(config) {
    const enabled = $("#post-process-enabled");
    const naming = $("#post-process-naming-template");
    const watermarkEnabled = $("#watermark-enabled");
    const watermarkText = $("#watermark-text");
    const watermarkFontSize = $("#watermark-font-size");
    const watermarkColor = $("#watermark-color");
    const watermarkOpacity = $("#watermark-opacity");
    const watermarkOpacityValue = $("#watermark-opacity-value");
    const watermarkPosition = $("#watermark-position");
    const watermarkImagePath = $("#watermark-image-path");
    const watermarkImageScale = $("#watermark-image-scale");
    const watermarkImageScaleValue = $("#watermark-image-scale-value");
    const exifEnabled = $("#exif-enabled");
    const exifArtist = $("#exif-artist");
    const exifCopyright = $("#exif-copyright");
    const exifDescription = $("#exif-description");
    if (!enabled) return;

    enabled.checked = Boolean(config.enabled);
    naming.value = config.naming_template || "";

    const watermark = config.watermark || {};
    watermarkEnabled.checked = Boolean(watermark.enabled);
    watermarkText.value = watermark.text || "";
    watermarkFontSize.value = String(watermark.font_size ?? 24);
    watermarkColor.value = watermark.color || "#FFFFFF";
    const opacityPercent = Math.round(
      Math.max(0, Math.min(1, Number(watermark.opacity ?? 0.7))) * 100
    );
    watermarkOpacity.value = String(opacityPercent);
    watermarkOpacityValue.textContent = `${opacityPercent}%`;
    watermarkPosition.value = watermark.position || "bottom-right";

    const watermarkType = watermark.type === "image" ? "image" : "text";
    setWatermarkType(watermarkType);

    const imagePath = watermark.image_path || "";
    if (watermarkImagePath) {
      watermarkImagePath.textContent = imagePath
        ? shortenImagePath(imagePath)
        : "未选择";
      watermarkImagePath.dataset.path = imagePath;
    }
    const scalePercent = Math.round(
      Math.max(5, Math.min(100, Number(watermark.image_scale ?? 0.2) * 100))
    );
    if (watermarkImageScale) {
      watermarkImageScale.value = String(scalePercent);
    }
    if (watermarkImageScaleValue) {
      watermarkImageScaleValue.textContent = `${scalePercent}%`;
    }

    toggleWatermarkControls(watermarkEnabled.checked);

    const exif = config.exif || {};
    exifEnabled.checked = Boolean(exif.enabled);
    exifArtist.value = exif.artist || "";
    exifCopyright.value = exif.copyright || "";
    exifDescription.value = exif.description || "";
    toggleExifControls(exifEnabled.checked);

    renderNamingPreview();
  }

  function shortenImagePath(path) {
    const segments = String(path).split(/[\\/]/);
    if (segments.length <= 2) return path;
    return `…/${segments.slice(-2).join("/")}`;
  }

  function setWatermarkType(type) {
    const radio = document.querySelector(
      `input[name="watermark-type"][value="${type}"]`
    );
    if (radio) radio.checked = true;
    const textFields = $(".watermark-text-fields");
    const imageFields = $(".watermark-image-fields");
    if (textFields) textFields.hidden = type !== "text";
    if (imageFields) imageFields.hidden = type !== "image";
  }

  function toggleWatermarkControls(enabled) {
    const controls = $(".watermark-controls");
    if (controls) controls.hidden = !enabled;
  }

  async function chooseWatermarkImage() {
    const button = $("#watermark-image-choose");
    const preview = $("#watermark-image-path");
    if (!button) return;
    button.disabled = true;
    try {
      const response = await PlateApp.bridge.call("choose_watermark_image");
      if (!response.accepted) {
        if (response.message) PlateApp.toast.show(response.message);
        return;
      }
      if (preview) {
        preview.textContent = shortenImagePath(response.path);
        preview.dataset.path = response.path;
      }
      PlateApp.toast.show("已选择水印图片。");
    } catch (error) {
      PlateApp.toast.show(`无法选择水印图片：${error.message || error}`);
    } finally {
      button.disabled = false;
    }
  }

  function toggleExifControls(enabled) {
    const controls = $(".exif-controls");
    if (controls) controls.hidden = !enabled;
  }

  function renderNamingPreview() {
    const template = $("#post-process-naming-template");
    const preview = $("#naming-preview-text");
    if (!template || !preview) return;
    const value = template.value.trim();
    if (!value) {
      preview.textContent = "—";
      return;
    }
    if (namingPreviewTimer) clearTimeout(namingPreviewTimer);
    namingPreviewTimer = setTimeout(async () => {
      try {
        const response = await PlateApp.bridge.call(
          "preview_naming",
          value,
          NAMING_SAMPLE
        );
        preview.textContent = response.preview || "—";
      } catch (error) {
        preview.textContent = "预览失败";
      }
    }, 300);
  }

  function collectPostProcessConfig() {
    const opacityValue = Number($("#watermark-opacity").value || 70) / 100;
    const selectedTypeRadio = document.querySelector(
      "input[name='watermark-type']:checked"
    );
    const watermarkType = selectedTypeRadio
      ? selectedTypeRadio.value
      : "text";
    const imagePathPreview = $("#watermark-image-path");
    const imagePath =
      imagePathPreview && imagePathPreview.dataset.path
        ? imagePathPreview.dataset.path
        : "";
    const imageScaleValue =
      Number($("#watermark-image-scale").value || 20) / 100;
    return {
      enabled: $("#post-process-enabled").checked,
      naming_template: $("#post-process-naming-template").value || "",
      watermark: {
        enabled: $("#watermark-enabled").checked,
        type: watermarkType,
        text: $("#watermark-text").value || "",
        font_size: Number($("#watermark-font-size").value || 24),
        color: $("#watermark-color").value || "#FFFFFF",
        opacity: opacityValue,
        position: $("#watermark-position").value || "bottom-right",
        margin: 16,
        image_path: imagePath,
        image_scale: imageScaleValue
      },
      exif: {
        enabled: $("#exif-enabled").checked,
        artist: $("#exif-artist").value || "",
        copyright: $("#exif-copyright").value || "",
        description: $("#exif-description").value || ""
      }
    };
  }

  async function savePostProcessConfig() {
    const button = $("#save-post-process-button");
    if (!button) return;
    button.disabled = true;
    try {
      const response = await PlateApp.bridge.call(
        "set_post_process_config",
        collectPostProcessConfig()
      );
      PlateApp.toast.show(response.message || "后处理配置已保存。");
    } catch (error) {
      PlateApp.toast.show(`无法保存后处理配置：${error.message || error}`);
    } finally {
      button.disabled = false;
    }
  }

  function renderWatchFolders(folders) {
    const list = $("#watch-folders-list");
    if (!list) return;
    list.innerHTML = "";
    if (!folders || !folders.length) {
      const empty = document.createElement("p");
      empty.className = "watch-folder-empty";
      empty.textContent = "还没有登记监视文件夹。点击下方按钮添加商拍素材文件夹。";
      list.appendChild(empty);
      return;
    }
    folders.forEach((folder) => {
      const row = document.createElement("div");
      row.className = "watch-folder-row";
      if (folder.error) row.classList.add("is-error");
      if (!folder.enabled) row.classList.add("is-disabled");

      const pathCol = document.createElement("div");
      pathCol.className = "watch-folder-path";
      const pathMain = document.createElement("span");
      pathMain.className = "watch-folder-path-main";
      pathMain.textContent = folder.path;
      pathMain.title = folder.path;
      pathCol.appendChild(pathMain);
      if (folder.error) {
        const error = document.createElement("span");
        error.className = "watch-folder-error";
        error.textContent = folder.error;
        pathCol.appendChild(error);
      }
      row.appendChild(pathCol);

      const toggle = document.createElement("label");
      toggle.className = "watch-folder-toggle";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = Boolean(folder.enabled);
      checkbox.addEventListener("change", () =>
        toggleWatchFolder(folder.path, checkbox.checked)
      );
      const toggleLabel = document.createElement("span");
      toggleLabel.textContent = folder.enabled ? "启用" : "已停用";
      toggle.appendChild(checkbox);
      toggle.appendChild(toggleLabel);
      row.appendChild(toggle);

      const remove = document.createElement("button");
      remove.className = "watch-folder-remove";
      remove.type = "button";
      remove.textContent = "移除";
      remove.addEventListener("click", () => removeWatchFolder(folder.path));
      row.appendChild(remove);

      list.appendChild(row);
    });
  }

  async function refreshWatchFolders() {
    try {
      const folders = await PlateApp.bridge.call("list_watch_folders");
      renderWatchFolders(folders);
      PlateApp.store.patch({ watchFolders: folders }, "watch_folders_refreshed");
    } catch (error) {
      PlateApp.toast.show(`无法刷新监视文件夹：${error.message || error}`);
    }
  }

  async function addWatchFolder() {
    const button = $("#add-watch-folder-button");
    button.disabled = true;
    try {
      const response = await PlateApp.bridge.call("add_watch_folder");
      if (!response.accepted) {
        if (response.message) PlateApp.toast.show(response.message);
        return;
      }
      PlateApp.toast.show("已添加监视文件夹。");
      await refreshWatchFolders();
    } catch (error) {
      PlateApp.toast.show(`无法添加监视文件夹：${error.message || error}`);
    } finally {
      button.disabled = false;
    }
  }

  async function removeWatchFolder(path) {
    const accepted = await PlateApp.dialog.confirm({
      title: "移除监视文件夹？",
      description: "移除后该文件夹的新照片将不再自动处理。已处理的记录会保留。",
      confirmLabel: "移除"
    });
    if (!accepted) return;
    try {
      await PlateApp.bridge.call("remove_watch_folder", path);
      await refreshWatchFolders();
    } catch (error) {
      PlateApp.toast.show(`无法移除监视文件夹：${error.message || error}`);
    }
  }

  async function toggleWatchFolder(path, enabled) {
    try {
      await PlateApp.bridge.call("set_watch_folder_enabled", path, enabled);
      await refreshWatchFolders();
    } catch (error) {
      PlateApp.toast.show(`无法切换监视状态：${error.message || error}`);
      await refreshWatchFolders();
    }
  }

  function init() {
    $("#preset").addEventListener("change", savePreset);
    $("#default-mask-margin").addEventListener("input", (event) => {
      renderMaskMargin(event.currentTarget.value);
    });
    $("#default-mask-margin").addEventListener("change", (event) => {
      return saveMaskMargin(event.currentTarget.value);
    });
    $("#default-mask-margin-number").addEventListener("change", (event) => {
      return saveMaskMargin(event.currentTarget.value);
    });
    const addWatchButton = $("#add-watch-folder-button");
    if (addWatchButton) addWatchButton.addEventListener("click", addWatchFolder);
    initPostProcessControls();
    $("#export-diagnostics-button").addEventListener("click", async () => {
      const button = $("#export-diagnostics-button");
      button.disabled = true;
      try {
        const response = await PlateApp.bridge.call("export_diagnostics");
        if (response.message) PlateApp.toast.show(response.message);
      } catch (error) {
        PlateApp.toast.show(`无法导出诊断包：${error.message || error}`);
      } finally {
        button.disabled = false;
      }
    });
    document.querySelectorAll(".support-document").forEach((button) => {
      button.addEventListener("click", async () => {
        button.disabled = true;
        try {
          const opened = await PlateApp.bridge.call(
            "open_support_document",
            button.dataset.document
          );
          if (!opened) PlateApp.toast.show("帮助文档缺失，请重新安装应用。");
        } catch (error) {
          PlateApp.toast.show(`无法打开帮助文档：${error.message || error}`);
        } finally {
          button.disabled = false;
        }
      });
    });
  }

  function initPostProcessControls() {
    const naming = $("#post-process-naming-template");
    if (naming) {
      naming.addEventListener("input", renderNamingPreview);
    }
    const watermarkEnabled = $("#watermark-enabled");
    if (watermarkEnabled) {
      watermarkEnabled.addEventListener("change", (event) => {
        toggleWatermarkControls(event.currentTarget.checked);
      });
    }
    document
      .querySelectorAll('input[name="watermark-type"]')
      .forEach((radio) => {
        radio.addEventListener("change", (event) => {
          setWatermarkType(event.currentTarget.value);
        });
      });
    const imageChooseButton = $("#watermark-image-choose");
    if (imageChooseButton) {
      imageChooseButton.addEventListener("click", chooseWatermarkImage);
    }
    const imageScale = $("#watermark-image-scale");
    const imageScaleValue = $("#watermark-image-scale-value");
    if (imageScale && imageScaleValue) {
      imageScale.addEventListener("input", (event) => {
        imageScaleValue.textContent = `${event.currentTarget.value}%`;
      });
    }
    const exifEnabled = $("#exif-enabled");
    if (exifEnabled) {
      exifEnabled.addEventListener("change", (event) => {
        toggleExifControls(event.currentTarget.checked);
      });
    }
    const opacity = $("#watermark-opacity");
    const opacityValue = $("#watermark-opacity-value");
    if (opacity && opacityValue) {
      opacity.addEventListener("input", (event) => {
        opacityValue.textContent = `${event.currentTarget.value}%`;
      });
    }
    const saveButton = $("#save-post-process-button");
    if (saveButton) {
      saveButton.addEventListener("click", savePostProcessConfig);
    }
  }

  PlateApp.settings = {
    hydrate,
    init,
    refreshWatchFolders,
    renderWatchFolders
  };
})();
