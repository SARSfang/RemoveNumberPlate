# Portions of the DB post-processing algorithm are adapted from PaddleOCR,
# Copyright (c) 2020 PaddlePaddle Authors, Apache License 2.0.
"""Paddle reference adapter for the PP-Vehicle plate detector."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from shutil import copy2
from typing import Any, cast

import cv2
import numpy as np
import pyclipper
from numpy.typing import NDArray
from shapely.geometry import Polygon

from app.config import AppPaths
from app.domain.detection import BoundingBox, Detection
from app.infrastructure.paddle_runtime import configure_nvidia_dll_search_path


class PaddleDetectorError(RuntimeError):
    """The optional Paddle detector could not be initialized or executed."""


def _contains_non_ascii(path: Path) -> bool:
    try:
        str(path.resolve()).encode("ascii")
    except UnicodeEncodeError:
        return True
    return False


def stage_paddle_model(
    model_dir: Path,
    runtime_root: Path | None = None,
    required_files: tuple[str, ...] = ("inference.pdmodel", "inference.pdiparams"),
) -> Path:
    """Copy a model to an ASCII runtime path when Paddle cannot open its path."""

    if not _contains_non_ascii(model_dir):
        return model_dir
    root = runtime_root or (AppPaths.default().data_dir / "runtime_models")
    if _contains_non_ascii(root):
        raise PaddleDetectorError(f"Paddle runtime path must contain ASCII only: {root}")
    target = root / model_dir.name
    target.mkdir(parents=True, exist_ok=True)
    for filename in required_files:
        source = model_dir / filename
        if not source.is_file():
            raise PaddleDetectorError(f"missing Paddle inference file: {source}")
        destination = target / filename
        if not destination.is_file() or destination.stat().st_size != source.stat().st_size:
            copy2(source, destination)
    return target


def resize_for_db(
    image_bgr: NDArray[np.uint8],
    limit_side_len: int = 960,
    limit_type: str = "max",
) -> tuple[NDArray[np.uint8], tuple[int, int, float, float]]:
    """Resize to a multiple of 32 using PaddleOCR's detector convention."""

    if image_bgr.ndim != 3 or image_bgr.shape[2] != 3:
        raise ValueError("image must have HxWx3 shape")
    source_height, source_width = image_bgr.shape[:2]
    if source_height <= 0 or source_width <= 0:
        raise ValueError("image dimensions must be positive")
    if limit_side_len < 32:
        raise ValueError("limit_side_len must be at least 32")

    if limit_type == "max":
        ratio = min(1.0, limit_side_len / max(source_height, source_width))
    elif limit_type == "min":
        ratio = max(1.0, limit_side_len / min(source_height, source_width))
    else:
        raise ValueError("limit_type must be 'max' or 'min'")

    resized_height = max(int(round(source_height * ratio / 32) * 32), 32)
    resized_width = max(int(round(source_width * ratio / 32) * 32), 32)
    resized = np.asarray(
        cv2.resize(image_bgr, (resized_width, resized_height)),
        dtype=np.uint8,
    )
    shape = (
        source_height,
        source_width,
        resized_height / float(source_height),
        resized_width / float(source_width),
    )
    return resized, shape


def normalize_for_db(image_bgr: NDArray[np.uint8]) -> NDArray[np.float32]:
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(1, 1, 3)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(1, 1, 3)
    normalized = (image_bgr.astype(np.float32) / 255.0 - mean) / std
    return np.ascontiguousarray(normalized.transpose(2, 0, 1)[None, ...])


def _ordered_min_box(contour: NDArray[np.int32]) -> tuple[NDArray[np.float32], float]:
    rectangle = cv2.minAreaRect(contour)
    points = sorted(cv2.boxPoints(rectangle).tolist(), key=lambda point: point[0])
    left = sorted(points[:2], key=lambda point: point[1])
    right = sorted(points[2:], key=lambda point: point[1])
    ordered = np.array([left[0], right[0], right[1], left[1]], dtype=np.float32)
    return ordered, float(min(rectangle[1]))


def _box_score(probability: NDArray[np.float32], box: NDArray[np.float32]) -> float:
    height, width = probability.shape
    x_min = int(np.clip(np.floor(box[:, 0].min()), 0, width - 1))
    x_max = int(np.clip(np.ceil(box[:, 0].max()), 0, width - 1))
    y_min = int(np.clip(np.floor(box[:, 1].min()), 0, height - 1))
    y_max = int(np.clip(np.ceil(box[:, 1].max()), 0, height - 1))
    mask = np.zeros((y_max - y_min + 1, x_max - x_min + 1), dtype=np.uint8)
    shifted = box.copy()
    shifted[:, 0] -= x_min
    shifted[:, 1] -= y_min
    cv2.fillPoly(mask, [shifted.reshape(-1, 2).astype(np.int32)], (1,))
    return float(cv2.mean(probability[y_min : y_max + 1, x_min : x_max + 1], mask)[0])


def _unclip(box: NDArray[np.float32], ratio: float) -> list[list[tuple[int, int]]]:
    polygon = Polygon(box)
    if polygon.length <= 0:
        return []
    distance = polygon.area * ratio / polygon.length
    offset = pyclipper.PyclipperOffset()
    path = [(int(round(x)), int(round(y))) for x, y in box]
    offset.AddPath(path, pyclipper.JT_ROUND, pyclipper.ET_CLOSEDPOLYGON)
    return cast(list[list[tuple[int, int]]], offset.Execute(distance))


def decode_db_map(
    probability: NDArray[np.float32],
    source_shape: tuple[int, int, float, float],
    threshold: float = 0.3,
    box_threshold: float = 0.6,
    unclip_ratio: float = 1.5,
    max_candidates: int = 1000,
) -> list[Detection]:
    """Decode a DB probability map to axis-aligned source-image detections."""

    if probability.ndim != 2:
        raise ValueError("probability map must have HxW shape")
    source_height, source_width, _, _ = source_shape
    bitmap = (probability > threshold).astype(np.uint8)
    contours, _ = cv2.findContours(bitmap * 255, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    detections: list[Detection] = []
    map_height, map_width = probability.shape

    for contour in contours[:max_candidates]:
        box, short_side = _ordered_min_box(np.asarray(contour, dtype=np.int32))
        if short_side < 3:
            continue
        score = _box_score(probability, box)
        if score < box_threshold:
            continue
        expanded = _unclip(box, unclip_ratio)
        if len(expanded) != 1:
            continue
        expanded_contour = np.asarray(expanded[0], dtype=np.int32).reshape(-1, 1, 2)
        expanded_box, expanded_short_side = _ordered_min_box(expanded_contour)
        if expanded_short_side < 5:
            continue

        x_values = expanded_box[:, 0] / map_width * source_width
        y_values = expanded_box[:, 1] / map_height * source_height
        x1 = float(np.clip(x_values.min(), 0, source_width))
        y1 = float(np.clip(y_values.min(), 0, source_height))
        x2 = float(np.clip(x_values.max(), 0, source_width))
        y2 = float(np.clip(y_values.max(), 0, source_height))
        if x2 <= x1 or y2 <= y1:
            continue
        detections.append(Detection(BoundingBox(x1, y1, x2, y2), score))

    return detections


class PaddlePlateDetector:
    """Reference implementation used to validate the official artifact."""

    def __init__(
        self,
        model_dir: Path,
        *,
        use_gpu: bool = True,
        limit_side_len: int = 960,
        limit_type: str = "max",
        threshold: float = 0.3,
        box_threshold: float = 0.6,
        runtime_root: Path | None = None,
    ) -> None:
        model_dir = stage_paddle_model(model_dir, runtime_root)
        model_file = model_dir / "inference.pdmodel"
        params_file = model_dir / "inference.pdiparams"
        if not model_file.is_file() or not params_file.is_file():
            raise PaddleDetectorError(f"missing Paddle inference files in {model_dir}")

        configure_nvidia_dll_search_path()
        try:
            inference = import_module("paddle.inference")
            config = inference.Config(str(model_file), str(params_file))
            if use_gpu:
                config.enable_use_gpu(512, 0)
            else:
                config.disable_gpu()
                config.set_cpu_math_library_num_threads(4)
            config.switch_ir_optim(True)
            config.disable_glog_info()
            self._predictor: Any = inference.create_predictor(config)
        except Exception as error:
            raise PaddleDetectorError(f"failed to initialize Paddle detector: {error}") from error

        self._input_name = self._predictor.get_input_names()[0]
        self._output_name = self._predictor.get_output_names()[0]
        self._limit_side_len = limit_side_len
        self._limit_type = limit_type
        self._threshold = threshold
        self._box_threshold = box_threshold

    def detect(self, image_rgb: NDArray[np.uint8]) -> list[Detection]:
        if image_rgb.dtype != np.uint8:
            raise ValueError("image must use uint8 pixels")
        image_bgr = np.ascontiguousarray(image_rgb[:, :, ::-1])
        resized, shape = resize_for_db(
            image_bgr,
            limit_side_len=self._limit_side_len,
            limit_type=self._limit_type,
        )
        tensor = normalize_for_db(resized)
        try:
            input_handle = self._predictor.get_input_handle(self._input_name)
            input_handle.reshape(tensor.shape)
            input_handle.copy_from_cpu(tensor)
            self._predictor.run()
            output_handle = self._predictor.get_output_handle(self._output_name)
            output = output_handle.copy_to_cpu()
        except Exception as error:
            raise PaddleDetectorError(f"Paddle inference failed: {error}") from error

        probability = np.asarray(output, dtype=np.float32)
        if probability.ndim != 4 or probability.shape[0] != 1:
            raise PaddleDetectorError(f"unexpected detector output shape: {probability.shape}")
        return decode_db_map(
            probability[0, 0],
            shape,
            threshold=self._threshold,
            box_threshold=self._box_threshold,
        )
