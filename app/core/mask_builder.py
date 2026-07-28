"""Build perspective-aware full-plate masks from detector polygons."""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot

import cv2
import numpy as np
import pyclipper
from numpy.typing import NDArray

from app.domain.detection import Detection, Quadrilateral

MINIMUM_MARGIN_RATIO = -0.15
MAXIMUM_MARGIN_RATIO = 0.35


@dataclass(frozen=True, slots=True)
class PlateMaskPolicy:
    """A proportional polygon margin covering the physical plate border."""

    margin_ratio: float = 0.08

    def __post_init__(self) -> None:
        if not MINIMUM_MARGIN_RATIO <= self.margin_ratio <= MAXIMUM_MARGIN_RATIO:
            raise ValueError(
                f"mask margin must be between {MINIMUM_MARGIN_RATIO} "
                f"and {MAXIMUM_MARGIN_RATIO}"
            )


DEFAULT_PLATE_MASK_POLICY = PlateMaskPolicy()


def _short_side(polygon: Quadrilateral) -> float:
    edges = [
        hypot(second[0] - first[0], second[1] - first[1])
        for first, second in zip(
            polygon.points,
            polygon.points[1:] + polygon.points[:1],
            strict=True,
        )
    ]
    return min((edges[0] + edges[2]) / 2.0, (edges[1] + edges[3]) / 2.0)


def offset_polygon(
    polygon: Quadrilateral,
    margin_ratio: float,
) -> list[tuple[int, int]]:
    """Offset a plate outline by a proportion of its shorter side."""

    if not MINIMUM_MARGIN_RATIO <= margin_ratio <= MAXIMUM_MARGIN_RATIO:
        raise ValueError(
            f"mask margin must be between {MINIMUM_MARGIN_RATIO} "
            f"and {MAXIMUM_MARGIN_RATIO}"
        )
    path = [(round(x), round(y)) for x, y in polygon.points]
    distance = _short_side(polygon) * margin_ratio
    if abs(distance) < 0.5:
        return path
    offset = pyclipper.PyclipperOffset()
    offset.AddPath(path, pyclipper.JT_ROUND, pyclipper.ET_CLOSEDPOLYGON)
    candidates = offset.Execute(distance)
    if not candidates:
        raise ValueError("mask margin removes the entire polygon")
    result = max(candidates, key=lambda candidate: abs(pyclipper.Area(candidate)))
    if len(result) < 3:
        raise ValueError("mask margin produced an invalid polygon")
    return [(int(x), int(y)) for x, y in result]


def build_plate_mask(
    image_shape: tuple[int, int],
    detections: list[Detection],
    policy: PlateMaskPolicy = DEFAULT_PLATE_MASK_POLICY,
) -> NDArray[np.uint8]:
    """Return a binary white-means-remove mask following plate perspective."""

    height, width = image_shape
    if height <= 0 or width <= 0:
        raise ValueError("image dimensions must be positive")
    mask = np.zeros((height, width), dtype=np.uint8)
    for detection in detections:
        points = offset_polygon(detection.effective_polygon, policy.margin_ratio)
        clipped = np.asarray(
            [
                (
                    min(max(x, 0), width - 1),
                    min(max(y, 0), height - 1),
                )
                for x, y in points
            ],
            dtype=np.int32,
        )
        cv2.fillPoly(mask, [clipped], (255.0,))
    return mask
