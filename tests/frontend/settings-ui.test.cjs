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
    "#export-diagnostics-button"
  ];
  const elements = Object.fromEntries(selectors.map((selector) => [
    selector,
    createElement()
  ]));
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
        return elements[selector];
      },
      querySelectorAll() {
        return [];
      }
    }
  };
  vm.runInNewContext(source, context);
  return { calls, elements, settings: context.window.PlateApp.settings };
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
