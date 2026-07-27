(() => {
  "use strict";
  const frame = document.querySelector("#app");
  frame.addEventListener("load", () => {
    const doc = frame.contentDocument;
    doc.querySelectorAll(".page").forEach((page) => page.classList.remove("is-active"));
    doc.querySelector("#page-review").classList.add("is-active");
    doc.querySelectorAll(".nav-item").forEach((button) => {
      button.classList.toggle("is-active", button.dataset.page === "review");
    });
    doc.querySelector("#review-empty").hidden = true;
    doc.querySelector("#review-workspace").hidden = false;
    doc.querySelector("#review-queue-count").textContent = "3";
    doc.querySelector("#review-badge").hidden = false;
    doc.querySelector("#review-badge").textContent = "3";
    doc.querySelector("#review-list").innerHTML = `
      <button class="review-item is-active"><strong>IMG_4821.jpg</strong><span>1 个候选区域 · 原图未修改</span></button>
      <button class="review-item"><strong>夜景_014.jpg</strong><span>2 个候选区域 · 原图未修改</span></button>
      <button class="review-item"><strong>侧面成片_07.tif</strong><span>1 个候选区域 · 原图未修改</span></button>`;
    doc.querySelector("#review-file-name").textContent = "IMG_4821.jpg";
    doc.querySelector("#review-risk-text").textContent = "检测置信度较低，原图尚未修改";
    doc.querySelector("#canvas-loading").hidden = true;

    const image = new Image();
    image.addEventListener("load", () => {
      const canvas = doc.querySelector("#review-canvas");
      const ratio = frame.contentWindow.devicePixelRatio || 1;
      canvas.width = Math.round(canvas.clientWidth * ratio);
      canvas.height = Math.round(canvas.clientHeight * ratio);
      const context = canvas.getContext("2d");
      context.scale(ratio, ratio);
      const scale = Math.min(canvas.clientWidth / image.width, canvas.clientHeight / image.height) * .92;
      const width = image.width * scale;
      const height = image.height * scale;
      const x = (canvas.clientWidth - width) / 2;
      const y = (canvas.clientHeight - height) / 2;
      context.drawImage(image, x, y, width, height);
      context.fillStyle = "rgba(240, 180, 76, .34)";
      context.strokeStyle = "#FFD184";
      context.lineWidth = 2;
      context.setLineDash([8, 5]);
      context.fillRect(x + width * .53, y + height * .54, width * .12, height * .09);
      context.strokeRect(x + width * .53, y + height * .54, width * .12, height * .09);
    });
    image.src = "/testdata/public/ppvehicleplate.jpg";
  });
})();
