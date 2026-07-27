"""ONNX Runtime adapter for the official pre-converted MI-GAN pipeline."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from app.infrastructure.paddle_runtime import configure_nvidia_dll_search_path


class InpainterError(RuntimeError):
    """The inpainting runtime or model failed."""


def prepare_migan_inputs(
    image_rgb: NDArray[np.uint8],
    mask: NDArray[np.uint8],
) -> tuple[NDArray[np.uint8], NDArray[np.uint8]]:
    """Convert white-means-remove input to MI-GAN's white-means-known mask."""

    if image_rgb.dtype != np.uint8 or image_rgb.ndim != 3 or image_rgb.shape[2] != 3:
        raise ValueError("image must be an HxWx3 uint8 RGB array")
    if mask.dtype != np.uint8 or mask.ndim != 2:
        raise ValueError("mask must be an HxW uint8 array")
    if mask.shape != image_rgb.shape[:2]:
        raise ValueError("mask dimensions must match the image")
    image_tensor = np.ascontiguousarray(image_rgb.transpose(2, 0, 1)[None, ...])
    known_mask = np.where(mask > 0, 0, 255).astype(np.uint8)
    mask_tensor = np.ascontiguousarray(known_mask[None, None, ...])
    return image_tensor, mask_tensor


def finalize_migan_output(
    output: NDArray[np.uint8],
    image_rgb: NDArray[np.uint8],
    mask: NDArray[np.uint8],
) -> NDArray[np.uint8]:
    """Validate output and guarantee untouched pixels remain bit-identical."""

    expected_shape = (1, 3, image_rgb.shape[0], image_rgb.shape[1])
    if output.shape != expected_shape:
        raise InpainterError(
            f"unexpected MI-GAN output shape: {output.shape}, expected {expected_shape}"
        )
    generated = np.ascontiguousarray(output[0].transpose(1, 2, 0))
    result = image_rgb.copy()
    selected = mask > 0
    result[selected] = generated[selected]
    return result


class MiganInpainter:
    """Inference-only MI-GAN adapter; no training framework is required."""

    def __init__(self, model_path: Path, *, use_gpu: bool = True) -> None:
        if not model_path.is_file():
            raise InpainterError(f"MI-GAN model not found: {model_path}")
        configure_nvidia_dll_search_path()
        try:
            runtime = import_module("onnxruntime")
            available = runtime.get_available_providers()
            providers = ["CPUExecutionProvider"]
            if use_gpu and "CUDAExecutionProvider" in available:
                providers.insert(0, "CUDAExecutionProvider")
            options = runtime.SessionOptions()
            options.log_severity_level = 3
            self._session: Any = runtime.InferenceSession(
                str(model_path),
                sess_options=options,
                providers=providers,
            )
        except Exception as error:
            raise InpainterError(f"failed to initialize MI-GAN: {error}") from error

        input_names = {value.name for value in self._session.get_inputs()}
        if input_names != {"image", "mask"}:
            raise InpainterError(f"unexpected MI-GAN inputs: {sorted(input_names)}")
        outputs = self._session.get_outputs()
        if len(outputs) != 1:
            raise InpainterError(f"unexpected MI-GAN output count: {len(outputs)}")
        self._output_name = outputs[0].name
        self.providers = tuple(self._session.get_providers())

    def inpaint(
        self,
        image_rgb: NDArray[np.uint8],
        mask: NDArray[np.uint8],
    ) -> NDArray[np.uint8]:
        image_tensor, mask_tensor = prepare_migan_inputs(image_rgb, mask)
        if not np.any(mask):
            return image_rgb.copy()
        try:
            raw_output = self._session.run(
                [self._output_name],
                {"image": image_tensor, "mask": mask_tensor},
            )[0]
        except Exception as error:
            raise InpainterError(f"MI-GAN inference failed: {error}") from error
        output = np.asarray(raw_output, dtype=np.uint8)
        return finalize_migan_output(output, image_rgb, mask)
