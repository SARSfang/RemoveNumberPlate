const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function createElement() {
  return {
    value: "",
    textContent: "",
    hidden: false,
    disabled: false,
    title: "",
    dataset: {},
    style: {},
    listeners: {},
    attributes: {},
    addEventListener(name, callback) {
      this.listeners[name] = callback;
    },
    setAttribute(name, value) {
      this.attributes[name] = String(value);
    }
  };
}

function loadSettingsModule() {
  const source = fs.readFileSync(
    path.join(__dirname, "../../app/web/settings/settings.js"),
    "utf8"
  );
  const selectors = [
    "#gpu-name",
    "#runtime-name",
    "#model-state",
    "#webview2-version",
    "#preset",
    "#default-mask-margin",
    "#default-mask-margin-number",
    "#default-mask-margin-value",
    "#default-mask-margin-warning",
    "#export-diagnostics-button",
    "#post-process-enabled",
    "#post-process-naming-template",
    "#naming-preview-text",
    "#watermark-enabled",
    "#watermark-text",
    "#watermark-font-size",
    "#watermark-color",
    "#watermark-opacity",
    "#watermark-opacity-value",
    "#watermark-position",
    "#watermark-image-choose",
    "#watermark-image-path",
    "#watermark-image-scale",
    "#watermark-image-scale-value",
    "#exif-enabled",
    "#exif-artist",
    "#exif-copyright",
    "#exif-description",
    "#save-post-process-button",
    ".watermark-controls",
    ".watermark-text-fields",
    ".watermark-image-fields",
    ".exif-controls"
  ];
  const elements = Object.fromEntries(selectors.map((selector) => [
    selector,
    createElement()
  ]));
  // Radio inputs need a `checked` flag and `value`. Setting `checked = true`
  // on one radio in the group should deselect the other (mimics browser
  // behavior for inputs with the same `name`).
  const textRadio = createElement();
  textRadio.value = "text";
  const imageRadio = createElement();
  imageRadio.value = "image";
  let selectedType = "text";
  Object.defineProperty(textRadio, "checked", {
    get() { return selectedType === "text"; },
    set(value) { if (value) selectedType = "text"; }
  });
  Object.defineProperty(imageRadio, "checked", {
    get() { return selectedType === "image"; },
    set(value) { if (value) selectedType = "image"; }
  });
  const radioByName = { text: textRadio, image: imageRadio };
  const calls = [];
  const context = {
    window: {
      PlateApp: {
        bridge: {
          async call(method, ...args) {
            calls.push([method, ...args]);
            return { accepted: true, message: "已保存" };
          }
        },
        toast: { show() {} }
      }
    },
    document: {
      querySelector(selector) {
        if (selector.startsWith("input[name=") || selector.startsWith("input[name='")) {
          if (selector.includes('[value="text"]')) return textRadio;
          if (selector.includes('[value="image"]')) return imageRadio;
          return selectedType === "image" ? imageRadio : textRadio;
        }
        return elements[selector];
      },
      querySelectorAll(selector) {
        if (selector === 'input[name="watermark-type"]') {
          return [textRadio, imageRadio];
        }
        return [];
      }
    }
  };
  vm.runInNewContext(source, context);
  return {
    calls,
    elements,
    radioByName,
    settings: context.window.PlateApp.settings
  };
}

test("global mask margin hydrates, warns, and saves as a percentage", async () => {
  const fixture = loadSettingsModule();
  const range = fixture.elements["#default-mask-margin"];

  fixture.settings.init();
  fixture.settings.hydrate({
    gpu: "GPU",
    runtime: "ONNX",
    models_ready: true,
    webview2_version: "138",
    preset: "balanced",
    mask_margin_percent: 35
  });

  assert.equal(range.value, "35");
  assert.equal(range.attributes["aria-valuetext"], "+35%");

  range.value = "100";
  range.listeners.input({ currentTarget: range });
  assert.equal(fixture.elements["#default-mask-margin-value"].textContent, "+100%");
  assert.equal(fixture.elements["#default-mask-margin-warning"].hidden, false);

  await range.listeners.change({ currentTarget: range });
  assert.deepEqual(fixture.calls.at(-1), ["set_mask_margin", 100]);
  assert.equal(range.dataset.savedValue, "100");
});

test("all stylesheet custom-property references are defined", () => {
  const styles = path.join(__dirname, "../../app/web/styles");
  const files = fs.readdirSync(styles).filter((name) => name.endsWith(".css"));
  const contents = files.map((name) =>
    fs.readFileSync(path.join(styles, name), "utf8")
  ).join("\n");
  const definitions = new Set(
    [...contents.matchAll(/--([a-z0-9-]+)\s*:/g)].map((match) => match[1])
  );
  const references = new Set(
    [...contents.matchAll(/var\(--([a-z0-9-]+)/g)].map((match) => match[1])
  );

  assert.deepEqual(
    [...references].filter((name) => !definitions.has(name)),
    []
  );
});

test("watermark type image hydrates and toggles image fields visible", () => {
  const fixture = loadSettingsModule();
  fixture.settings.init();
  fixture.settings.hydrate({
    gpu: "GPU",
    runtime: "ONNX",
    models_ready: true,
    webview2_version: "138",
    preset: "balanced",
    mask_margin_percent: 35,
    post_process_config: {
      enabled: true,
      watermark: {
        enabled: true,
        type: "image",
        image_path: "C:/logos/watermark.png",
        image_scale: 0.5,
        opacity: 0.6,
        position: "center"
      }
    }
  });

  const imagePath = fixture.elements["#watermark-image-path"];
  const imageScale = fixture.elements["#watermark-image-scale"];
  const imageScaleValue = fixture.elements["#watermark-image-scale-value"];
  const textFields = fixture.elements[".watermark-text-fields"];
  const imageFields = fixture.elements[".watermark-image-fields"];

  assert.equal(imagePath.dataset.path, "C:/logos/watermark.png");
  assert.equal(imageScale.value, "50");
  assert.equal(imageScaleValue.textContent, "50%");
  assert.equal(textFields.hidden, true);
  assert.equal(imageFields.hidden, false);
});

test("watermark type text keeps text fields visible and hides image fields", () => {
  const fixture = loadSettingsModule();
  fixture.settings.init();
  fixture.settings.hydrate({
    gpu: "GPU",
    runtime: "ONNX",
    models_ready: true,
    webview2_version: "138",
    preset: "balanced",
    mask_margin_percent: 35,
    post_process_config: {
      enabled: true,
      watermark: {
        enabled: true,
        type: "text",
        text: "© acme"
      }
    }
  });

  const textFields = fixture.elements[".watermark-text-fields"];
  const imageFields = fixture.elements[".watermark-image-fields"];
  assert.equal(textFields.hidden, false);
  assert.equal(imageFields.hidden, true);
});

test("collectPostProcessConfig includes watermark type, image_path, image_scale", () => {
  const fixture = loadSettingsModule();
  fixture.settings.init();
  fixture.settings.hydrate({
    gpu: "GPU",
    runtime: "ONNX",
    models_ready: true,
    webview2_version: "138",
    preset: "balanced",
    mask_margin_percent: 35,
    post_process_config: {
      enabled: true,
      watermark: {
        enabled: true,
        type: "image",
        image_path: "/tmp/logo.png",
        image_scale: 0.3
      }
    }
  });

  // Mock collectPostProcessConfig via a direct call by saving post process
  // settings: the save handler invokes bridge.call with the collected payload.
  const saveButton = fixture.elements["#save-post-process-button"];
  saveButton.listeners.click({ currentTarget: saveButton });

  // Wait for the async handler to push the call.
  // node:test runs synchronous code in the same tick; we need to await microtasks.
  return new Promise((resolve) => {
    setTimeout(() => {
      const call = fixture.calls.find((entry) => entry[0] === "set_post_process_config");
      assert.ok(call, "expected set_post_process_config call");
      const payload = call[1];
      assert.equal(payload.watermark.type, "image");
      assert.equal(payload.watermark.image_path, "/tmp/logo.png");
      assert.equal(payload.watermark.image_scale, 0.3);
      resolve();
    }, 0);
  });
});
