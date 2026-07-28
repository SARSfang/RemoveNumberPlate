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

test("quadrilateral validation rejects self-intersection and reversed order", () => {
  const review = loadReviewModule();

  assert.equal(review.isValidQuadrilateral([
    [10, 20], [100, 15], [105, 55], [5, 60]
  ]), true);
  assert.equal(review.isValidQuadrilateral([
    [10, 20], [105, 55], [100, 15], [5, 60]
  ]), false);
  assert.equal(review.isValidQuadrilateral([
    [10, 20], [5, 60], [105, 55], [100, 15]
  ]), false);
});

test("polygon hit testing works for perspective plates", () => {
  const review = loadReviewModule();
  const points = [[10, 20], [100, 15], [105, 55], [5, 60]];

  assert.equal(review.pointInPolygon([50, 35], points), true);
  assert.equal(review.pointInPolygon([102, 18], points), false);
});

test("margin preview expands and contracts around the same center", () => {
  const review = loadReviewModule();
  const points = [[10, 20], [100, 20], [100, 60], [10, 60]];
  const expanded = review.expandedPolygon(points, 0.08);
  const contracted = review.expandedPolygon(points, -0.15);

  assert.ok(expanded[0][0] < points[0][0]);
  assert.ok(expanded[0][1] < points[0][1]);
  assert.ok(contracted[0][0] > points[0][0]);
  assert.ok(contracted[0][1] > points[0][1]);
});
