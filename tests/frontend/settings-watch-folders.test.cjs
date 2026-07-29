const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function makeElement(tag) {
  const el = {
    tagName: tag || "div",
    className: "",
    textContent: "",
    title: "",
    type: "",
    checked: false,
    hidden: false,
    disabled: false,
    value: "",
    dataset: {},
    style: {},
    attributes: {},
    children: [],
    listeners: {},
    _classes: new Set(),
    classList: {
      add(c) { el._classes.add(c); },
      toggle(c, force) {
        if (force === undefined) {
          el._classes.has(c) ? el._classes.delete(c) : el._classes.add(c);
        } else if (force) {
          el._classes.add(c);
        } else {
          el._classes.delete(c);
        }
      }
    },
    appendChild(child) {
      el.children.push(child);
      return child;
    },
    addEventListener(name, callback) {
      el.listeners[name] = callback;
    },
    setAttribute(name, value) {
      el.attributes[name] = String(value);
    }
  };
  return el;
}

function loadSettingsModule(foldersFromList) {
  const source = fs.readFileSync(
    path.join(__dirname, "../../app/web/settings/settings.js"),
    "utf8"
  );
  const listElement = makeElement("div");
  const addWatchButton = makeElement("button");
  const calls = [];
  const storePatches = [];
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
    "#watch-folders-list",
    "#add-watch-folder-button"
  ];
  const elements = Object.fromEntries(selectors.map((selector) => [
    selector,
    selector === "#watch-folders-list"
      ? listElement
      : selector === "#add-watch-folder-button"
        ? addWatchButton
        : makeElement(selector === "#preset" ? "select" : "input")
  ]));
  const context = {
    window: {
      PlateApp: {
        bridge: {
          async call(method, ...args) {
            calls.push([method, ...args]);
            if (method === "list_watch_folders") {
              return foldersFromList || [];
            }
            if (method === "add_watch_folder") {
              return { accepted: true, message: "", folder: { path: "/new", enabled: true, added_at: "t", error: null } };
            }
            if (method === "remove_watch_folder") {
              return { accepted: true, message: "" };
            }
            if (method === "set_watch_folder_enabled") {
              return { accepted: true, message: "" };
            }
            return { accepted: true, message: "" };
          }
        },
        toast: { show() {} },
        store: {
          patch(patch, reason) {
            storePatches.push({ patch, reason });
          }
        },
        dialog: {
          async confirm() { return true; }
        }
      }
    },
    document: {
      querySelector(selector) {
        return elements[selector] || null;
      },
      querySelectorAll() {
        return [];
      },
      createElement(tag) {
        return makeElement(tag);
      },
      getElementById() {
        return null;
      }
    }
  };
  vm.runInNewContext(source, context);
  return {
    calls,
    storePatches,
    listElement,
    addWatchButton,
    settings: context.window.PlateApp.settings
  };
}

test("renderWatchFolders shows empty message when no folders", () => {
  const fixture = loadSettingsModule([]);
  fixture.settings.renderWatchFolders([]);
  assert.equal(fixture.listElement.children.length, 1);
  const empty = fixture.listElement.children[0];
  assert.equal(empty.tagName, "p");
  assert.equal(empty.textContent.includes("还没有登记"), true);
});

test("renderWatchFolders builds a row per folder with path, toggle and remove", () => {
  const fixture = loadSettingsModule([]);
  const folders = [
    { path: "C:/shoot/a", enabled: true, added_at: "t1", error: null }
  ];
  fixture.settings.renderWatchFolders(folders);
  assert.equal(fixture.listElement.children.length, 1);
  const row = fixture.listElement.children[0];
  assert.equal(row.tagName, "div");
  assert.equal(row.className.includes("watch-folder-row"), true);
  // path column, toggle label, remove button
  assert.equal(row.children.length, 3);
  const pathCol = row.children[0];
  assert.equal(pathCol.className.includes("watch-folder-path"), true);
  assert.equal(pathCol.children[0].textContent, "C:/shoot/a");
  assert.equal(pathCol.children[0].title, "C:/shoot/a");
});

test("renderWatchFolders marks errored folders with is-error", () => {
  const fixture = loadSettingsModule([]);
  fixture.settings.renderWatchFolders([
    { path: "/bad", enabled: true, added_at: "t", error: "文件夹已删除" }
  ]);
  const row = fixture.listElement.children[0];
  assert.equal(row._classes.has("is-error"), true);
  const pathCol = row.children[0];
  // path + error span
  assert.equal(pathCol.children.length, 2);
  assert.equal(pathCol.children[1].textContent, "文件夹已删除");
});

test("toggle checkbox change calls set_watch_folder_enabled then refreshes", async () => {
  const fixture = loadSettingsModule([
    { path: "/x", enabled: true, added_at: "t", error: null }
  ]);
  fixture.settings.renderWatchFolders([
    { path: "/x", enabled: true, added_at: "t", error: null }
  ]);
  const row = fixture.listElement.children[0];
  const toggle = row.children[1];
  const checkbox = toggle.children[0];
  assert.equal(checkbox.type, "checkbox");
  assert.equal(checkbox.checked, true);
  await checkbox.listeners.change();
  assert.deepEqual(fixture.calls[0], ["set_watch_folder_enabled", "/x", true]);
  assert.deepEqual(fixture.calls[1], ["list_watch_folders"]);
  assert.equal(fixture.storePatches.some((p) => p.reason === "watch_folders_refreshed"), true);
});

test("remove button click calls remove_watch_folder then refreshes", async () => {
  const fixture = loadSettingsModule([
    { path: "/y", enabled: true, added_at: "t", error: null }
  ]);
  fixture.settings.renderWatchFolders([
    { path: "/y", enabled: true, added_at: "t", error: null }
  ]);
  const row = fixture.listElement.children[0];
  const remove = row.children[2];
  assert.equal(remove.tagName, "button");
  await remove.listeners.click();
  assert.deepEqual(fixture.calls[0], ["remove_watch_folder", "/y"]);
  assert.deepEqual(fixture.calls[1], ["list_watch_folders"]);
});

test("hydrate renders watch folders from bootstrap", () => {
  const fixture = loadSettingsModule([]);
  fixture.settings.hydrate({
    gpu: "GPU",
    runtime: "ONNX",
    models_ready: true,
    webview2_version: "138",
    preset: "balanced",
    mask_margin_percent: 35,
    watch_folders: [
      { path: "/hydrated", enabled: true, added_at: "t", error: null }
    ]
  });
  assert.equal(fixture.listElement.children.length, 1);
  const row = fixture.listElement.children[0];
  assert.equal(row.children[0].children[0].textContent, "/hydrated");
});

test("add button click calls add_watch_folder and refreshes", async () => {
  const fixture = loadSettingsModule([]);
  fixture.settings.init();
  await fixture.addWatchButton.listeners.click();
  assert.deepEqual(fixture.calls[0], ["add_watch_folder"]);
  assert.deepEqual(fixture.calls[1], ["list_watch_folders"]);
});
