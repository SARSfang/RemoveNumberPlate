"""ONNX Runtime adapters for the converted official Paddle detection models."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from app.domain.detection import Detection
from app.infrastructure.paddle_plate_detector import (
    decode_db_map,
    normalize_for_db,
    resize_for_db,
)
from app.infrastructure.paddle_vehicle_detector import (
    decode_vehicle_boxes,
    preprocess_vehicle_image,
)


class OnnxDetectorError(RuntimeError):
    """An ONNX detector could not be initialized or executed."""


def _create_session(model_path: Path) -> Any:
    if not model_path.is_file():
        raise OnnxDetectorError(f"missing ONNX detector model: {model_path}")
    try:
        runtime = import_module("onnxruntime")
        options = runtime.SessionOptions()
        options.graph_optimization_level = runtime.GraphOptimizationLevel.ORT_ENABLE_ALL
        return runtime.InferenceSession(
            str(model_path),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
    except Exception as error:
        raise OnnxDetectorError(f"failed to initialize ONNX detector: {error}") from error


class OnnxVehicleDetector:
    """PP-YOLOE-S vehicle detector running without the Paddle runtime."""

    def __init__(self, model_path: Path, *, confidence_threshold: float = 0.5) -> None:
        self._session = _create_session(model_path)
        self._confidence_threshold = confidence_threshold

    def detect(self, image_rgb: NDArray[np.uint8]) -> list[Detection]:
        image_tensor, scale_factor = preprocess_vehicle_image(image_rgb)
        try:
            outputs = self._session.run(
                None,
                {"image": image_tensor, "scale_factor": scale_factor},
            )
        except Exception as error:
            raise OnnxDetectorError(f"ONNX vehicle inference failed: {error}") from error
        boxes = next(
            (
                np.asarray(output, dtype=np.float32)
                for output in outputs
                if np.asarray(output).ndim == 2 and np.asarray(output).shape[1] == 6
            ),
            None,
        )
        if boxes is None:
            shapes = [tuple(np.asarray(output).shape) for output in outputs]
            raise OnnxDetectorError(f"unexpected vehicle model outputs: {shapes}")
        return decode_vehicle_boxes(
            boxes,
            (int(image_rgb.shape[0]), int(image_rgb.shape[1])),
            confidence_threshold=self._confidence_threshold,
        )


class OnnxPlateDetector:
    """PP-OCRv3 DB plate detector running without the Paddle runtime."""

    def __init__(
        self,
        model_path: Path,
        *,
        limit_side_len: int = 960,
        limit_type: str = "max",
        threshold: float = 0.3,
        box_threshold: float = 0.6,
    ) -> None:
        self._session = _create_session(model_path)
        self._input_name = self._session.get_inputs()[0].name
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
            outputs = self._session.run(None, {self._input_name: tensor})
        except Exception as error:
            raise OnnxDetectorError(f"ONNX plate inference failed: {error}") from error
        probability = np.asarray(outputs[0], dtype=np.float32)
        if probability.ndim != 4 or probability.shape[0] != 1:
            raise OnnxDetectorError(f"unexpected detector output shape: {probability.shape}")
        return decode_db_map(
            probability[0, 0],
            shape,
            threshold=self._threshold,
            box_threshold=self._box_threshold,
        )
