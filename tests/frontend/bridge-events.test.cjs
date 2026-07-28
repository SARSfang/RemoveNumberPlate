const test = require("node:test");
const assert = require("node:assert/strict");
const { initialState, reduceBackendEvent } = require("../../app/web/core/state.js");

test("pause, resume and finish are deterministic", () => {
  let state = { ...initialState(), running: true };
  state = reduceBackendEvent(state, {
    name: "paused",
    payload: { paused: true }
  });
  assert.equal(state.paused, true);
  state = reduceBackendEvent(state, {
    name: "paused",
    payload: { paused: false }
  });
  assert.equal(state.paused, false);
  state = reduceBackendEvent(state, {
    name: "batch_finished",
    payload: { cancelled: false }
  });
  assert.equal(state.running, false);
  assert.equal(state.processingId, null);
});

test("item completion preserves output availability and risks", () => {
  const seed = {
    ...initialState(),
    jobs: [{ job_id: "a", name: "a.jpg", index: 1, status: "detecting" }]
  };
  const state = reduceBackendEvent(seed, {
    name: "item_finished",
    payload: {
      job_id: "a",
      status: "review_required",
      elapsed: 0.5,
      output_available: false,
      detection_count: 2,
      risks: ["touches_edge"]
    }
  });

  assert.equal(state.jobs[0].status, "review_required");
  assert.equal(state.jobs[0].output_available, false);
  assert.deepEqual(state.jobs[0].risks, ["touches_edge"]);
});
