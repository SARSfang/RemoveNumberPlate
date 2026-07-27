"""Vehicle-first license-plate detection pipeline."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from app.core.detector import Detector
from app.domain.detection import BoundingBox, Detection


class VehicleFirstPlateDetector:
    """Detect vehicles, then detect plates inside each vehicle crop."""

    def __init__(
        self,
        vehicle_detector: Detector,
        plate_detector: Detector,
        *,
        crop_margin_ratio: float = 0.03,
    ) -> None:
        if crop_margin_ratio < 0:
            raise ValueError("crop_margin_ratio must be non-negative")
        self._vehicle_detector = vehicle_detector
        self._plate_detector = plate_detector
        self._crop_margin_ratio = crop_margin_ratio

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
                results.append(
                    Detection(
                        BoundingBox(
                            plate_box.x1 + x1,
                            plate_box.y1 + y1,
                            plate_box.x2 + x1,
                            plate_box.y2 + y1,
                        ),
                        plate.confidence,
                    )
                )
        return results
