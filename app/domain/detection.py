"""License-plate detection value objects."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

Point = tuple[float, float]


def _cross(first: Point, second: Point, third: Point) -> float:
    return (second[0] - first[0]) * (third[1] - second[1]) - (
        second[1] - first[1]
    ) * (third[0] - second[0])


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
class Quadrilateral:
    """Convex clockwise plate outline in normalized source-image pixels."""

    points: tuple[Point, ...]

    def __post_init__(self) -> None:
        if len(self.points) != 4:
            raise ValueError("quadrilateral must contain exactly four points")
        normalized = tuple((float(point[0]), float(point[1])) for point in self.points)
        object.__setattr__(self, "points", normalized)
        if any(
            not isfinite(coordinate) or coordinate < 0
            for point in normalized
            for coordinate in point
        ):
            raise ValueError("quadrilateral coordinates must be finite and non-negative")

        crosses = tuple(
            _cross(normalized[index], normalized[(index + 1) % 4], normalized[(index + 2) % 4])
            for index in range(4)
        )
        if any(value <= 1e-6 for value in crosses):
            raise ValueError(
                "quadrilateral points must form a clockwise convex polygon"
            )
        if self.area <= 1e-6:
            raise ValueError("quadrilateral must have positive area")

    @property
    def area(self) -> float:
        return 0.5 * sum(
            first[0] * second[1] - second[0] * first[1]
            for first, second in zip(
                self.points,
                self.points[1:] + self.points[:1],
                strict=True,
            )
        )

    @property
    def bounding_box(self) -> BoundingBox:
        x_values = [point[0] for point in self.points]
        y_values = [point[1] for point in self.points]
        return BoundingBox(
            min(x_values),
            min(y_values),
            max(x_values),
            max(y_values),
        )

    def clipped(self, image_width: int, image_height: int) -> Quadrilateral:
        if image_width <= 0 or image_height <= 0:
            raise ValueError("image dimensions must be positive")
        return Quadrilateral(
            tuple(
                (
                    min(max(point[0], 0.0), float(image_width)),
                    min(max(point[1], 0.0), float(image_height)),
                )
                for point in self.points
            )
        )

    @classmethod
    def from_box(cls, box: BoundingBox) -> Quadrilateral:
        return cls(
            (
                (box.x1, box.y1),
                (box.x2, box.y1),
                (box.x2, box.y2),
                (box.x1, box.y2),
            )
        )


@dataclass(frozen=True, slots=True)
class Detection:
    """A decoded detector result."""

    box: BoundingBox
    confidence: float
    source_tile: int | None = None
    polygon: Quadrilateral | None = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if self.source_tile is not None and self.source_tile < 0:
            raise ValueError("source_tile must be non-negative")

    @property
    def effective_polygon(self) -> Quadrilateral:
        return self.polygon or Quadrilateral.from_box(self.box)
