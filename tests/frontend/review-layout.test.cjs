const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function loadReviewModule() {
  const source = fs.readFileSync(
    path.join(__dirname, "../../app/web/review/editor.js"),
    "utf8"
  );
  const context = {
    window: {
      PlateApp: {},
      requestAnimationFrame() {}
    },
    document: {
      querySelector() {
        throw new Error("DOM access is not expected in this pure helper test");
      },
      querySelectorAll() {
        return [];
      }
    }
  };
  vm.runInNewContext(source, context);
  return context.window.PlateApp.review;
}

test("review activation refits only a hidden-layout scale", () => {
  const review = loadReviewModule();

  assert.equal(review.needsRefit(0.00048, 1186, 751), true);
  assert.equal(review.needsRefit(0.92, 1186, 751), false);
  assert.equal(review.needsRefit(0.00048, 1, 751), false);
  assert.equal(review.needsRefit(Number.NaN, 1186, 751), false);
});

test("tiny accidental rectangle drags are ignored", () => {
  const review = loadReviewModule();

  assert.equal(review.isMeaningfulRectangle({
    type: "rectangle",
    start: [100, 100],
    end: [102, 140]
  }, 1), false);
  assert.equal(review.isMeaningfulRectangle({
    type: "rectangle",
    start: [100, 100],
    end: [110, 140]
  }, 1), true);
  assert.equal(review.isMeaningfulRectangle({
    type: "brush_add",
    points: [[100, 100]]
  }, 1), false);
});
