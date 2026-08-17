from dataclasses import dataclass

import numpy as np

from app.core.two_stage_detector import (
    VehicleFirstPlateDetector,
    merge_detections,
)
from app.domain.detection import BoundingBox, Detection, Quadrilateral


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
    pipeline = VehicleFirstPlateDetector(
        vehicle,
        plate,
        crop_margin_ratio=0,
        fallback_to_full_image=False,
    )

    result = pipeline.detect(np.zeros((100, 120, 3), dtype=np.uint8))

    assert plate.last_shape == (40, 60, 3)
    assert result == [Detection(BoundingBox(25, 30, 45, 40), 0.9)]


def test_two_stage_detector_offsets_plate_polygon() -> None:
    vehicle = StubDetector([Detection(BoundingBox(20, 10, 80, 50), 0.95)])
    polygon = Quadrilateral(((5, 20), (25, 18), (24, 30), (4, 31)))
    plate = StubDetector([Detection(polygon.bounding_box, 0.9, polygon=polygon)])
    pipeline = VehicleFirstPlateDetector(
        vehicle,
        plate,
        crop_margin_ratio=0,
        fallback_to_full_image=False,
    )

    result = pipeline.detect(np.zeros((100, 120, 3), dtype=np.uint8))

    assert result[0].polygon == Quadrilateral(
        ((25, 30), (45, 28), (44, 40), (24, 41))
    )


def test_fallback_detects_plates_outside_vehicles() -> None:
    vehicle = StubDetector([])
    plate = StubDetector([Detection(BoundingBox(10, 10, 30, 22), 0.8)])
    pipeline = VehicleFirstPlateDetector(vehicle, plate, crop_margin_ratio=0)

    result = pipeline.detect(np.zeros((100, 120, 3), dtype=np.uint8))

    assert result == [Detection(BoundingBox(10, 10, 30, 22), 0.8)]


def test_fallback_merges_and_dedups_overlapping_plates() -> None:
    """The crop result wins over a lower-confidence full-image duplicate."""
    vehicle = StubDetector([Detection(BoundingBox(20, 10, 80, 50), 0.95)])
    # Crop detections are offset into source coordinates; full-image detections
    # are already in source coordinates. The stub branches on input size.
    class BranchingPlateDetector:
        def detect(self, image_rgb: np.ndarray) -> list[Detection]:
            if image_rgb.shape == (40, 60, 3):
                # Inside the (20, 10, 80, 50) crop at crop_relative coords.
                return [
                    Detection(BoundingBox(5, 20, 25, 30), 0.9),
                ]
            # Full-image fallback: a lower-confidence duplicate plus a new plate.
            return [
                Detection(BoundingBox(24, 29, 46, 41), 0.6),
                Detection(BoundingBox(100, 100, 140, 122), 0.7),
            ]

    pipeline = VehicleFirstPlateDetector(
        vehicle,
        BranchingPlateDetector(),
        crop_margin_ratio=0,
    )

    result = pipeline.detect(np.zeros((100, 120, 3), dtype=np.uint8))

    assert result == [
        Detection(BoundingBox(25, 30, 45, 40), 0.9),
        Detection(BoundingBox(100, 100, 140, 122), 0.7),
    ]


def test_merge_detections_keeps_distinct_plates() -> None:
    first = Detection(BoundingBox(10, 10, 30, 22), 0.9)
    second = Detection(BoundingBox(100, 100, 140, 122), 0.7)
    duplicate = Detection(BoundingBox(11, 11, 29, 21), 0.8)

    result = merge_detections([first, duplicate, second])

    assert result == [first, second]


def test_merge_detections_prefers_higher_confidence() -> None:
    high = Detection(BoundingBox(10, 10, 30, 22), 0.95)
    low = Detection(BoundingBox(11, 11, 29, 21), 0.4)

    result = merge_detections([low, high])

    assert result == [high]
