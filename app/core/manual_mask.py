"""Convert persisted review-editor commands into a binary source-space mask."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import cv2
import numpy as np
from numpy.typing import NDArray

from app.core.mask_builder import build_plate_mask
from app.domain.detection import Detection

MAX_COMMANDS = 10_000
MAX_POINTS_PER_STROKE = 20_000


def _number(value: object, name: str) -> float:
    if not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    return float(value)


def _bounded_point(value: object, width: int, height: int) -> tuple[int, int]:
    if not isinstance(value, Sequence) or len(value) != 2:
        raise ValueError("point must contain x and y")
    x = min(max(round(_number(value[0], "x")), 0), width - 1)
    y = min(max(round(_number(value[1], "y")), 0), height - 1)
    return x, y


def build_manual_mask(
    image_shape: tuple[int, int],
    detections: Sequence[Detection],
    commands: Sequence[Mapping[str, object]],
) -> NDArray[np.uint8]:
    """Apply bounded add/erase commands over the retained automatic mask."""

    height, width = image_shape
    if height <= 0 or width <= 0:
        raise ValueError("image dimensions must be positive")
    if len(commands) > MAX_COMMANDS:
        raise ValueError("too many mask commands")

    removed: set[int] = set()
    for command in commands:
        index = command.get("index")
        if command.get("type") == "remove_detection" and isinstance(index, int):
            removed.add(index)
    active_detections = [
        detection for index, detection in enumerate(detections) if index not in removed
    ]
    mask = build_plate_mask(image_shape, active_detections)

    for command in commands:
        command_type = command.get("type")
        if command_type == "rectangle":
            start = _bounded_point(command.get("start"), width, height)
            end = _bounded_point(command.get("end"), width, height)
            x1, x2 = sorted((start[0], end[0]))
            y1, y2 = sorted((start[1], end[1]))
            if x2 > x1 and y2 > y1:
                cv2.rectangle(mask, (x1, y1), (x2, y2), (255.0,), thickness=-1)
        elif command_type in {"brush_add", "brush_erase"}:
            raw_points = command.get("points")
            if not isinstance(raw_points, Sequence) or not raw_points:
                continue
            if len(raw_points) > MAX_POINTS_PER_STROKE:
                raise ValueError("too many points in brush stroke")
            points = [_bounded_point(point, width, height) for point in raw_points]
            radius = min(
                max(round(_number(command.get("radius", 20), "radius")), 1),
                500,
            )
            color = (0.0,) if command_type == "brush_erase" else (255.0,)
            if len(points) == 1:
                cv2.circle(mask, points[0], radius, color, thickness=-1)
            else:
                for first, second in zip(points, points[1:], strict=False):
                    cv2.line(mask, first, second, color, thickness=radius * 2)
                cv2.circle(mask, points[-1], radius, color, thickness=-1)
    return mask
