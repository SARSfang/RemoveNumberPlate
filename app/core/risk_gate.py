"""Deterministic risk checks for automatic versus review-required output."""

from __future__ import annotations

from app.domain.detection import BoundingBox, Detection
from app.domain.job import RiskReason


def _intersection_over_union(first: BoundingBox, second: BoundingBox) -> float:
    x1 = max(first.x1, second.x1)
    y1 = max(first.y1, second.y1)
    x2 = min(first.x2, second.x2)
    y2 = min(first.y2, second.y2)
    intersection = max(x2 - x1, 0) * max(y2 - y1, 0)
    if intersection <= 0:
        return 0.0
    union = first.area + second.area - intersection
    return intersection / union if union > 0 else 0.0


def assess_detection_risks(
    image_shape: tuple[int, int],
    detections: list[Detection],
    *,
    auto_confidence: float = 0.60,
) -> tuple[RiskReason, ...]:
    """Return stable machine-readable reasons that require human review."""

    height, width = image_shape
    if height <= 0 or width <= 0:
        raise ValueError("image dimensions must be positive")
    risks: set[RiskReason] = set()
    for detection in detections:
        box = detection.box
        if detection.confidence < auto_confidence:
            risks.add(RiskReason.LOW_CONFIDENCE)
        if min(box.width, box.height) < 12 or box.area / (width * height) < 0.00004:
            risks.add(RiskReason.PLATE_TOO_SMALL)
        if box.x1 <= 2 or box.y1 <= 2 or box.x2 >= width - 2 or box.y2 >= height - 2:
            risks.add(RiskReason.TOUCHES_EDGE)
        aspect_ratio = box.width / box.height
        if aspect_ratio < 1 or aspect_ratio > 10 or box.area > width * height * 0.25:
            risks.add(RiskReason.ABNORMAL_BOX)

    for index, first in enumerate(detections):
        for second in detections[index + 1 :]:
            if _intersection_over_union(first.box, second.box) > 0.5:
                risks.add(RiskReason.OVERLAPPING_BOXES)
    return tuple(sorted(risks, key=str))
