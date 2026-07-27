"""License-plate detection value objects."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BoundingBox:
    """Axis-aligned box in orientation-normalized source-image pixels."""

    x1: float
    y1: float
    x2: float
    y2: float

    def __post_init__(self) -> None:
        if self.x1 < 0 or self.y1 < 0:
            raise ValueError("box coordinates must be non-negative")
        if self.x2 <= self.x1 or self.y2 <= self.y1:
            raise ValueError("box must have positive width and height")

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1

    @property
    def area(self) -> float:
        return self.width * self.height

    def clipped(self, image_width: int, image_height: int) -> BoundingBox:
        if image_width <= 0 or image_height <= 0:
            raise ValueError("image dimensions must be positive")
        x1 = min(max(self.x1, 0.0), float(image_width))
        y1 = min(max(self.y1, 0.0), float(image_height))
        x2 = min(max(self.x2, 0.0), float(image_width))
        y2 = min(max(self.y2, 0.0), float(image_height))
        if x2 <= x1 or y2 <= y1:
            raise ValueError("box does not intersect the image")
        return BoundingBox(x1, y1, x2, y2)


@dataclass(frozen=True, slots=True)
class Detection:
    """A decoded detector result."""

    box: BoundingBox
    confidence: float
    source_tile: int | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if self.source_tile is not None and self.source_tile < 0:
            raise ValueError("source_tile must be non-negative")
