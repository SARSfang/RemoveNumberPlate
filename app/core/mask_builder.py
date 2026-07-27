"""Build conservative full-plate masks from text-detector boxes."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from app.domain.detection import Detection


@dataclass(frozen=True, slots=True)
class PlateMaskPolicy:
    """Expansion ratios account for non-text plate borders and country strips."""

    left_by_height: float = 0.95
    right_by_height: float = 1.00
    top_by_height: float = 0.40
    bottom_by_height: float = 0.40

    def __post_init__(self) -> None:
        ratios = (
            self.left_by_height,
            self.right_by_height,
            self.top_by_height,
            self.bottom_by_height,
        )
        if any(value < 0 for value in ratios):
            raise ValueError("mask expansion ratios must be non-negative")


DEFAULT_PLATE_MASK_POLICY = PlateMaskPolicy()


def build_plate_mask(
    image_shape: tuple[int, int],
    detections: list[Detection],
    policy: PlateMaskPolicy = DEFAULT_PLATE_MASK_POLICY,
) -> NDArray[np.uint8]:
    """Return a binary white-means-remove mask covering the complete plate."""

    height, width = image_shape
    if height <= 0 or width <= 0:
        raise ValueError("image dimensions must be positive")
    mask = np.zeros((height, width), dtype=np.uint8)
    for detection in detections:
        box = detection.box
        x1 = max(int(np.floor(box.x1 - box.height * policy.left_by_height)), 0)
        y1 = max(int(np.floor(box.y1 - box.height * policy.top_by_height)), 0)
        x2 = min(
            int(np.ceil(box.x2 + box.height * policy.right_by_height)),
            width,
        )
        y2 = min(
            int(np.ceil(box.y2 + box.height * policy.bottom_by_height)),
            height,
        )
        if x2 > x1 and y2 > y1:
            mask[y1:y2, x1:x2] = 255
    return mask
