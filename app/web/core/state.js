(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) {
    root.PlateApp = root.PlateApp || {};
    root.PlateApp.state = api;
  }
})(typeof window !== "undefined" ? window : null, function () {
  "use strict";

  const FINAL_STATUSES = new Set([
    "completed",
    "review_required",
    "no_plate",
    "failed",
    "cancelled"
  ]);

  function initialState() {
    return {
      running: false,
      paused: false,
      total: 0,
      jobs: [],
      selectedId: null,
      processingId: null,
      previewMode: "following",
      preferredVariant: "result",
      modelsReady: false,
      bootstrap: null
    };
  }

  function cloneJob(value) {
    return {
      job_id: String(value.job_id),
      name: String(value.name || ""),
      index: Number(value.index || 0),
      status: String(value.status || "queued"),
      elapsed: value.elapsed == null ? null : Number(value.elapsed),
      detection_count: Number(value.detection_count || 0),
      risks: Array.isArray(value.risks) ? [...value.risks] : [],
      error: value.error ? String(value.error) : "",
      output_available: Boolean(value.output_available)
    };
  }

  function replaceJob(state, identifier, patch) {
    const index = state.jobs.findIndex((job) => job.job_id === identifier);
    if (index < 0) return state;
    const jobs = [...state.jobs];
    jobs[index] = { ...jobs[index], ...patch };
    return { ...state, jobs };
  }

  function reduceBackendEvent(current, event) {
    const state = current || initialState();
    const payload = event && event.payload ? event.payload : {};
    switch (event && event.name) {
      case "batch_accepted":
        return {
          ...initialState(),
          running: true,
          modelsReady: state.modelsReady,
          bootstrap: state.bootstrap
        };
      case "batch_discovered":
        return { ...state, total: Number(payload.total || 0) };
      case "batch_items_ready": {
        const jobs = Array.isArray(payload.items) ? payload.items.map(cloneJob) : [];
        return { ...state, jobs, total: jobs.length };
      }
      case "item_started": {
        const identifier = String(payload.job_id || "");
        const next = replaceJob(state, identifier, {
          status: "detecting",
          index: Number(payload.index || 0)
        });
        return {
          ...next,
          processingId: identifier,
          selectedId: state.previewMode === "following" ? identifier : state.selectedId
        };
      }
      case "item_finished": {
        const identifier = String(payload.job_id || "");
        return replaceJob(state, identifier, {
          status: String(payload.status || "failed"),
          elapsed: Number(payload.elapsed || 0),
          detection_count: Number(payload.detection_count || 0),
          risks: Array.isArray(payload.risks) ? [...payload.risks] : [],
          error: payload.error ? String(payload.error) : "",
          output_available: Boolean(payload.output_available)
        });
      }
      case "paused":
        return { ...state, paused: Boolean(payload.paused) };
      case "batch_finished":
        return {
          ...state,
          running: false,
          paused: false,
          processingId: null
        };
      default:
        return state;
    }
  }

  function counts(state) {
    const result = {
      completed: 0,
      review_required: 0,
      no_plate: 0,
      failed: 0,
      cancelled: 0,
      active: 0,
      finished: 0
    };
    state.jobs.forEach((job) => {
      if (Object.hasOwn(result, job.status)) result[job.status] += 1;
      if (FINAL_STATUSES.has(job.status)) result.finished += 1;
      else result.active += 1;
    });
    return result;
  }

  function createStore(seed) {
    let value = seed ? { ...initialState(), ...seed } : initialState();
    const listeners = new Set();
    return {
      get() {
        return value;
      },
      dispatch(event) {
        const next = reduceBackendEvent(value, event);
        if (next !== value) {
          value = next;
          listeners.forEach((listener) => listener(value, event));
        }
        return value;
      },
      patch(patch, reason) {
        value = { ...value, ...patch };
        listeners.forEach((listener) => listener(value, {
          name: reason || "state_patched",
          payload: patch
        }));
        return value;
      },
      subscribe(listener) {
        listeners.add(listener);
        return () => listeners.delete(listener);
      }
    };
  }

  class LruCache {
    constructor(limit) {
      this.limit = Math.max(1, Number(limit || 1));
      this.values = new Map();
    }

    get(key) {
      if (!this.values.has(key)) return undefined;
      const value = this.values.get(key);
      this.values.delete(key);
      this.values.set(key, value);
      return value;
    }

    set(key, value) {
      if (this.values.has(key)) this.values.delete(key);
      this.values.set(key, value);
      while (this.values.size > this.limit) {
        this.values.delete(this.values.keys().next().value);
      }
    }

    has(key) {
      return this.values.has(key);
    }

    get size() {
      return this.values.size;
    }
  }

  return {
    FINAL_STATUSES,
    LruCache,
    counts,
    createStore,
    initialState,
    reduceBackendEvent
  };
});
