"""Paddle adapter for the official PP-YOLOE-S vehicle detector."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from numpy.typing import NDArray

from app.domain.detection import BoundingBox, Detection
from app.infrastructure.paddle_plate_detector import (
    PaddleDetectorError,
    stage_paddle_model,
)
from app.infrastructure.paddle_runtime import configure_nvidia_dll_search_path


def preprocess_vehicle_image(
    image_rgb: NDArray[np.uint8],
    target_size: tuple[int, int] = (640, 640),
) -> tuple[NDArray[np.float32], NDArray[np.float32]]:
    """Apply the preprocessing declared by the official inference.yml."""

    if image_rgb.dtype != np.uint8 or image_rgb.ndim != 3 or image_rgb.shape[2] != 3:
        raise ValueError("image must be an HxWx3 uint8 RGB array")
    source_height, source_width = image_rgb.shape[:2]
    target_height, target_width = target_size
    resized = cv2.resize(
        image_rgb,
        (target_width, target_height),
        interpolation=cv2.INTER_CUBIC,
    )
    normalized = resized.astype(np.float32) / 255.0
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    normalized = (normalized - mean) / std
    image_tensor = np.ascontiguousarray(normalized.transpose(2, 0, 1)[None, ...])
    scale_factor = np.array(
        [[target_height / source_height, target_width / source_width]],
        dtype=np.float32,
    )
    return image_tensor, scale_factor


def decode_vehicle_boxes(
    boxes: NDArray[np.floating[Any]],
    image_shape: tuple[int, int],
    confidence_threshold: float = 0.5,
) -> list[Detection]:
    """Decode PaddleDetection rows: class, score, x1, y1, x2, y2."""

    if boxes.ndim != 2 or boxes.shape[1] != 6:
        raise ValueError(f"vehicle boxes must have Nx6 shape, got {boxes.shape}")
    height, width = image_shape
    detections: list[Detection] = []
    for row in boxes:
        score = float(row[1])
        if score < confidence_threshold:
            continue
        x1 = float(np.clip(row[2], 0, width))
        y1 = float(np.clip(row[3], 0, height))
        x2 = float(np.clip(row[4], 0, width))
        y2 = float(np.clip(row[5], 0, height))
        if x2 > x1 and y2 > y1:
            detections.append(Detection(BoundingBox(x1, y1, x2, y2), score))
    return detections


class PaddleVehicleDetector:
    """Inference-only adapter for the official PP-YOLOE-S_vehicle artifact."""

    def __init__(
        self,
        model_dir: Path,
        *,
        use_gpu: bool = True,
        confidence_threshold: float = 0.5,
        runtime_root: Path | None = None,
    ) -> None:
        model_dir = stage_paddle_model(
            model_dir,
            runtime_root,
            required_files=("inference.json", "inference.pdiparams", "inference.yml"),
        )
        model_file = model_dir / "inference.json"
        params_file = model_dir / "inference.pdiparams"

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
            raise PaddleDetectorError(
                f"failed to initialize Paddle vehicle detector: {error}"
            ) from error

        self._input_names = tuple(self._predictor.get_input_names())
        self._output_names = tuple(self._predictor.get_output_names())
        self._confidence_threshold = confidence_threshold

    def detect(self, image_rgb: NDArray[np.uint8]) -> list[Detection]:
        image_tensor, scale_factor = preprocess_vehicle_image(image_rgb)
        inputs = {"image": image_tensor, "scale_factor": scale_factor}
        try:
            for name in self._input_names:
                if name not in inputs:
                    raise PaddleDetectorError(f"unexpected vehicle model input: {name}")
                handle = self._predictor.get_input_handle(name)
                value = inputs[name]
                handle.reshape(value.shape)
                handle.copy_from_cpu(value)
            self._predictor.run()
            outputs = [
                np.asarray(
                    self._predictor.get_output_handle(name).copy_to_cpu(),
                    dtype=np.float32,
                )
                for name in self._output_names
            ]
        except PaddleDetectorError:
            raise
        except Exception as error:
            raise PaddleDetectorError(f"Paddle vehicle inference failed: {error}") from error

        boxes = next(
            (
                output
                for output in outputs
                if output.ndim == 2 and output.shape[1] == 6
            ),
            None,
        )
        if boxes is None:
            shapes = [tuple(output.shape) for output in outputs]
            raise PaddleDetectorError(f"unexpected vehicle model outputs: {shapes}")
        return decode_vehicle_boxes(
            boxes,
            (int(image_rgb.shape[0]), int(image_rgb.shape[1])),
            confidence_threshold=self._confidence_threshold,
        )
