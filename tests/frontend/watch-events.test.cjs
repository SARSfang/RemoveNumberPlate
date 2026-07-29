const test = require("node:test");
const assert = require("node:assert/strict");
const {
  initialState,
  reduceBackendEvent,
  watchActive
} = require("../../app/web/core/state.js");

test("initialState includes watch folder fields", () => {
  const state = initialState();
  assert.deepEqual(state.watchFolders, []);
  assert.equal(state.watchFolderCount, 0);
  assert.equal(state.watchCaptured, 0);
  assert.equal(state.watchProcessed, 0);
  assert.equal(state.watchScanInProgress, false);
});

test("watch_status updates counts from active_count/captured/processed", () => {
  const state = reduceBackendEvent(initialState(), {
    name: "watch_status",
    payload: { active_count: 2, captured: 5, processed: 3 }
  });
  assert.equal(state.watchFolderCount, 2);
  assert.equal(state.watchCaptured, 5);
  assert.equal(state.watchProcessed, 3);
});

test("watch_scan_started and complete toggle the scan flag", () => {
  let state = reduceBackendEvent(initialState(), {
    name: "watch_scan_started",
    payload: {}
  });
  assert.equal(state.watchScanInProgress, true);
  state = reduceBackendEvent(state, {
    name: "watch_scan_complete",
    payload: { collected_count: 4, cancelled: false }
  });
  assert.equal(state.watchScanInProgress, false);
});

test("watch_folder_error does not mutate state", () => {
  const before = initialState();
  const after = reduceBackendEvent(before, {
    name: "watch_folder_error",
    payload: { folder: "/x", error: "boom" }
  });
  assert.equal(after, before);
});

test("batch_accepted preserves watch state across batch reset", () => {
  const seed = {
    ...initialState(),
    watchFolders: [{ path: "/a", enabled: true, added_at: "t", error: null }],
    watchFolderCount: 1,
    watchCaptured: 7,
    watchProcessed: 4,
    watchScanInProgress: false
  };
  const state = reduceBackendEvent(seed, {
    name: "batch_accepted",
    payload: {}
  });
  assert.deepEqual(state.watchFolders, [
    { path: "/a", enabled: true, added_at: "t", error: null }
  ]);
  assert.equal(state.watchFolderCount, 1);
  assert.equal(state.watchCaptured, 7);
  assert.equal(state.watchProcessed, 4);
  assert.equal(state.running, true);
});

test("watchActive is true when an enabled error-free folder is registered", () => {
  const state = {
    ...initialState(),
    watchFolders: [{ path: "/a", enabled: true, added_at: "t", error: null }]
  };
  assert.equal(watchActive(state), true);
});

test("watchActive is false when all folders are disabled or errored", () => {
  const state = {
    ...initialState(),
    watchFolders: [
      { path: "/a", enabled: false, added_at: "t", error: null },
      { path: "/b", enabled: true, added_at: "t", error: "boom" }
    ]
  };
  assert.equal(watchActive(state), false);
});

test("watchActive is true when watch_status reports active watchers", () => {
  const state = { ...initialState(), watchFolderCount: 1 };
  assert.equal(watchActive(state), true);
});
