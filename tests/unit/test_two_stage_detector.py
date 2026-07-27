from dataclasses import dataclass

import numpy as np

from app.core.two_stage_detector import VehicleFirstPlateDetector
from app.domain.detection import BoundingBox, Detection


@dataclass
class StubDetector:
    detections: list[Detection]
    last_shape: tuple[int, ...] | None = None

    def detect(self, image_rgb: np.ndarray) -> list[Detection]:
        self.last_shape = image_rgb.shape
        return self.detections


def test_two_stage_detector_offsets_crop_results() -> None:
    vehicle = StubDetector([Detection(BoundingBox(20, 10, 80, 50), 0.95)])
    plate = StubDetector([Detection(BoundingBox(5, 20, 25, 30), 0.9)])
    pipeline = VehicleFirstPlateDetector(vehicle, plate, crop_margin_ratio=0)

    result = pipeline.detect(np.zeros((100, 120, 3), dtype=np.uint8))

    assert plate.last_shape == (40, 60, 3)
    assert result == [Detection(BoundingBox(25, 30, 45, 40), 0.9)]
