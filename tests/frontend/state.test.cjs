const test = require("node:test");
const assert = require("node:assert/strict");
const {
  LruCache,
  counts,
  initialState,
  reduceBackendEvent
} = require("../../app/web/core/state.js");

test("following mode tracks the item that starts processing", () => {
  let state = reduceBackendEvent(initialState(), {
    name: "batch_items_ready",
    payload: {
      items: [
        { job_id: "a", name: "a.jpg", index: 1, status: "queued" },
        { job_id: "b", name: "b.jpg", index: 2, status: "queued" }
      ]
    }
  });

  state = reduceBackendEvent(state, {
    name: "item_started",
    payload: { job_id: "b", index: 2 }
  });

  assert.equal(state.selectedId, "b");
  assert.equal(state.processingId, "b");
  assert.equal(state.jobs[1].status, "detecting");
});

test("pinned mode keeps the user's selected job", () => {
  const seed = {
    ...initialState(),
    previewMode: "pinned",
    selectedId: "a",
    jobs: [
      { job_id: "a", name: "a.jpg", index: 1, status: "queued" },
      { job_id: "b", name: "b.jpg", index: 2, status: "queued" }
    ]
  };

  const state = reduceBackendEvent(seed, {
    name: "item_started",
    payload: { job_id: "b", index: 2 }
  });

  assert.equal(state.selectedId, "a");
  assert.equal(state.processingId, "b");
});

test("finished jobs update counts without rebuilding unrelated jobs", () => {
  const seed = {
    ...initialState(),
    jobs: [
      { job_id: "a", name: "a.jpg", index: 1, status: "detecting" },
      { job_id: "b", name: "b.jpg", index: 2, status: "queued" }
    ]
  };

  const state = reduceBackendEvent(seed, {
    name: "item_finished",
    payload: {
      job_id: "a",
      status: "completed",
      elapsed: 1.2,
      output_available: true,
      detection_count: 1,
      risks: []
    }
  });

  assert.equal(state.jobs[0].status, "completed");
  assert.equal(state.jobs[1], seed.jobs[1]);
  assert.deepEqual(counts(state), {
    completed: 1,
    review_required: 0,
    no_plate: 0,
    failed: 0,
    cancelled: 0,
    active: 1,
    finished: 1
  });
});

test("LRU cache keeps a strict bounded size", () => {
  const cache = new LruCache(2);
  cache.set("a", 1);
  cache.set("b", 2);
  assert.equal(cache.get("a"), 1);
  cache.set("c", 3);

  assert.equal(cache.size, 2);
  assert.equal(cache.has("a"), true);
  assert.equal(cache.has("b"), false);
  assert.equal(cache.has("c"), true);
});
