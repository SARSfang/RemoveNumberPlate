"""Validate adjustment-editor commands before building a source-space mask."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite
from uuid import UUID

from app.core.mask_builder import (
    DEFAULT_MARGIN_RATIO,
    MAXIMUM_MARGIN_RATIO,
    MINIMUM_MARGIN_RATIO,
)
from app.domain.detection import Detection, Quadrilateral

MAX_COMMANDS = 10_000
MAX_POINTS_PER_STROKE = 20_000
MAX_BRUSH_RADIUS = 500.0


@dataclass(frozen=True, slots=True)
class ResolvedAdjustment:
    detections: tuple[Detection, ...]
    margin_ratio: float
    paint_commands: tuple[Mapping[str, object], ...]


def _number(value: object, name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{name} must be numeric")
    result = float(value)
    if not isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def bounded_point(
    value: object,
    width: int,
    height: int,
) -> tuple[float, float]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or len(value) != 2
    ):
        raise ValueError("point must contain x and y")
    x = _number(value[0], "x")
    y = _number(value[1], "y")
    if abs(x) > width * 10 or abs(y) > height * 10:
        raise ValueError("point is unreasonably far outside the image")
    return (
        min(max(x, 0.0), float(width)),
        min(max(y, 0.0), float(height)),
    )


def _polygon(value: object, width: int, height: int) -> Quadrilateral:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or len(value) != 4
    ):
        raise ValueError("polygon must contain four points")
    points = tuple(bounded_point(point, width, height) for point in value)
    return Quadrilateral(points)


def _target_id(command: Mapping[str, object]) -> str:
    target = command.get("target_id")
    if isinstance(target, str) and target:
        return target
    index = command.get("index")
    if isinstance(index, int) and index >= 0:
        return f"detection:{index}"
    raise ValueError("command target is missing")


def resolve_adjustment_commands(
    image_shape: tuple[int, int],
    detections: Sequence[Detection],
    commands: Sequence[Mapping[str, object]],
    *,
    default_margin_ratio: float = DEFAULT_MARGIN_RATIO,
) -> ResolvedAdjustment:
    """Apply structural commands and validate all paint commands."""

    height, width = image_shape
    if height <= 0 or width <= 0:
        raise ValueError("image dimensions must be positive")
    if len(commands) > MAX_COMMANDS:
        raise ValueError("too many mask commands")

    resolved: dict[str, Detection] = {
        f"detection:{index}": detection
        for index, detection in enumerate(detections)
    }
    if not MINIMUM_MARGIN_RATIO <= default_margin_ratio <= MAXIMUM_MARGIN_RATIO:
        raise ValueError("default margin must be between -0.30 and 1.00")
    margin_ratio = default_margin_ratio
    paint_commands: list[Mapping[str, object]] = []

    for command in commands:
        command_type = command.get("type")
        if command_type == "set_detection_polygon":
            target = _target_id(command)
            if target not in resolved:
                raise ValueError(f"unknown polygon target: {target}")
            polygon = _polygon(command.get("points"), width, height)
            previous = resolved[target]
            resolved[target] = Detection(
                polygon.bounding_box,
                previous.confidence,
                previous.source_tile,
                polygon,
            )
        elif command_type == "add_polygon":
            identifier = command.get("id")
            if not isinstance(identifier, str):
                raise ValueError("new polygon id is missing")
            try:
                UUID(identifier)
            except ValueError as error:
                raise ValueError("new polygon id must be a UUID") from error
            target = f"manual:{identifier}"
            if target in resolved:
                raise ValueError("new polygon id is already in use")
            polygon = _polygon(command.get("points"), width, height)
            resolved[target] = Detection(
                polygon.bounding_box,
                1.0,
                polygon=polygon,
            )
        elif command_type == "remove_detection":
            target = _target_id(command)
            if target not in resolved:
                raise ValueError(f"unknown polygon target: {target}")
            del resolved[target]
        elif command_type == "set_margin":
            margin_ratio = _number(
                command.get("value", command.get("margin_ratio")),
                "margin",
            )
            if not MINIMUM_MARGIN_RATIO <= margin_ratio <= MAXIMUM_MARGIN_RATIO:
                raise ValueError("margin must be between -0.30 and 1.00")
        elif command_type in {"brush_add", "brush_erase"}:
            raw_points = command.get("points")
            if (
                not isinstance(raw_points, Sequence)
                or isinstance(raw_points, (str, bytes))
                or not raw_points
            ):
                raise ValueError("brush stroke must contain points")
            if len(raw_points) > MAX_POINTS_PER_STROKE:
                raise ValueError("too many points in brush stroke")
            for point in raw_points:
                bounded_point(point, width, height)
            radius = _number(command.get("radius", 20), "radius")
            if not 1 <= radius <= MAX_BRUSH_RADIUS:
                raise ValueError("brush radius must be between 1 and 500")
            paint_commands.append(command)
        elif command_type == "rectangle":
            bounded_point(command.get("start"), width, height)
            bounded_point(command.get("end"), width, height)
            paint_commands.append(command)
        else:
            raise ValueError(f"unsupported adjustment command: {command_type!r}")

    return ResolvedAdjustment(
        tuple(resolved.values()),
        margin_ratio,
        tuple(paint_commands),
    )
