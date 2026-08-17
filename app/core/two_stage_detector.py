"""Vehicle-first license-plate detection pipeline."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from app.core.detector import Detector
from app.domain.detection import BoundingBox, Detection, Quadrilateral


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


def merge_detections(
    detections: list[Detection],
    *,
    iou_threshold: float = 0.6,
) -> list[Detection]:
    """Deduplicate overlapping detections, keeping higher-confidence boxes.

    Candidates are considered in descending confidence order; a candidate is
    kept only when its box overlaps every retained box by no more than
    ``iou_threshold``. Distinct plates (IoU below the threshold) are preserved.
    """

    if not 0.0 <= iou_threshold <= 1.0:
        raise ValueError("iou_threshold must be between 0 and 1")
    ordered = sorted(detections, key=lambda detection: detection.confidence, reverse=True)
    merged: list[Detection] = []
    for detection in ordered:
        if any(
            _intersection_over_union(detection.box, retained.box) > iou_threshold
            for retained in merged
        ):
            continue
        merged.append(detection)
    return merged


class VehicleFirstPlateDetector:
    """Detect vehicles, then detect plates inside each vehicle crop."""

    def __init__(
        self,
        vehicle_detector: Detector,
        plate_detector: Detector,
        *,
        crop_margin_ratio: float = 0.03,
        fallback_to_full_image: bool = True,
        merge_iou_threshold: float = 0.6,
    ) -> None:
        if crop_margin_ratio < 0:
            raise ValueError("crop_margin_ratio must be non-negative")
        if not 0.0 <= merge_iou_threshold <= 1.0:
            raise ValueError("merge_iou_threshold must be between 0 and 1")
        self._vehicle_detector = vehicle_detector
        self._plate_detector = plate_detector
        self._crop_margin_ratio = crop_margin_ratio
        self._fallback_to_full_image = fallback_to_full_image
        self._merge_iou_threshold = merge_iou_threshold

    def detect(self, image_rgb: NDArray[np.uint8]) -> list[Detection]:
        height, width = image_rgb.shape[:2]
        results: list[Detection] = []
        for vehicle in self._vehicle_detector.detect(image_rgb):
            box = vehicle.box
            margin_x = box.width * self._crop_margin_ratio
            margin_y = box.height * self._crop_margin_ratio
            x1 = max(int(np.floor(box.x1 - margin_x)), 0)
            y1 = max(int(np.floor(box.y1 - margin_y)), 0)
            x2 = min(int(np.ceil(box.x2 + margin_x)), width)
            y2 = min(int(np.ceil(box.y2 + margin_y)), height)
            if x2 <= x1 or y2 <= y1:
                continue
            crop = np.ascontiguousarray(image_rgb[y1:y2, x1:x2])
            for plate in self._plate_detector.detect(crop):
                plate_box = plate.box
                polygon = (
                    Quadrilateral(
                        tuple(
                            (point_x + x1, point_y + y1)
                            for point_x, point_y in plate.polygon.points
                        )
                    )
                    if plate.polygon is not None
                    else None
                )
                results.append(
                    Detection(
                        BoundingBox(
                            plate_box.x1 + x1,
                            plate_box.y1 + y1,
                            plate_box.x2 + x1,
                            plate_box.y2 + y1,
                        ),
                        plate.confidence,
                        polygon=polygon,
                    )
                )
        if self._fallback_to_full_image:
            results.extend(self._plate_detector.detect(image_rgb))
            results = merge_detections(
                results,
                iou_threshold=self._merge_iou_threshold,
            )
        return results
