"""Context-crop adapter for OpenCV's quantized LaMa ONNX model."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from numpy.typing import NDArray

from app.infrastructure.migan_inpainter import InpainterError


def _context_bounds(
    mask: NDArray[np.uint8],
    context_scale: float,
) -> tuple[int, int, int, int]:
    points = cv2.findNonZero((mask > 0).astype(np.uint8))
    if points is None:
        return (0, 0, mask.shape[1], mask.shape[0])
    x, y, width, height = cv2.boundingRect(points)
    side = max(int(round(max(width, height) * context_scale)), 64)
    side = min(side, mask.shape[0], mask.shape[1])
    center_x = x + width // 2
    center_y = y + height // 2
    x1 = min(max(center_x - side // 2, 0), mask.shape[1] - side)
    y1 = min(max(center_y - side // 2, 0), mask.shape[0] - side)
    return x1, y1, x1 + side, y1 + side


def split_mask_regions(
    mask: NDArray[np.uint8],
    min_area: int = 1,
) -> list[NDArray[np.uint8]]:
    """Split a binary mask into its connected components (8-connectivity).

    Each returned array holds only one connected component. Components whose
    area is below ``min_area`` are dropped; the default of 1 guarantees any
    non-zero region (including tiny brush remnants) is still processed.
    """

    if not np.any(mask):
        return []
    binary = (mask > 0).astype(np.uint8)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        binary, connectivity=8
    )
    regions: list[NDArray[np.uint8]] = []
    for label in range(1, num_labels):
        if stats[label, cv2.CC_STAT_AREA] < min_area:
            continue
        region = np.zeros_like(mask)
        region[labels == label] = 255
        regions.append(region)
    return regions


def _feathered_composite(
    original: NDArray[np.uint8],
    generated: NDArray[np.uint8],
    mask: NDArray[np.uint8],
    feather_radius: int,
) -> NDArray[np.uint8]:
    binary = (mask > 0).astype(np.float32)
    if feather_radius <= 0:
        alpha = binary
    else:
        kernel = feather_radius * 2 + 1
        alpha = np.asarray(
            cv2.GaussianBlur(binary, (kernel, kernel), feather_radius / 2),
            dtype=np.float32,
        )
        core = cv2.erode(
            binary,
            np.ones((kernel, kernel), dtype=np.uint8),
            iterations=1,
        )
        alpha[core > 0] = 1.0
    alpha = alpha[:, :, None]
    blended = generated.astype(np.float32) * alpha + original.astype(np.float32) * (
        1.0 - alpha
    )
    return np.clip(blended, 0, 255).astype(np.uint8)


class LamaInpainter:
    """LaMa inference on a square context crop around the selected region."""

    def __init__(
        self,
        model_path: Path,
        *,
        context_scale: float = 4.0,
        feather_radius: int = 12,
    ) -> None:
        if not model_path.is_file():
            raise InpainterError(f"LaMa model not found: {model_path}")
        if context_scale < 2:
            raise ValueError("context_scale must be at least 2")
        runtime = import_module("onnxruntime")
        options = runtime.SessionOptions()
        options.log_severity_level = 3
        try:
            self._session: Any = runtime.InferenceSession(
                str(model_path),
                sess_options=options,
                providers=["CPUExecutionProvider"],
            )
        except Exception as error:
            raise InpainterError(f"failed to initialize LaMa: {error}") from error
        self._context_scale = context_scale
        self._feather_radius = feather_radius

    def _inpaint_crop(
        self,
        image_rgb: NDArray[np.uint8],
        mask: NDArray[np.uint8],
    ) -> NDArray[np.uint8]:
        """Run LaMa on a single context crop and feathered-composite it back."""
        x1, y1, x2, y2 = _context_bounds(mask, self._context_scale)
        crop_rgb = np.ascontiguousarray(image_rgb[y1:y2, x1:x2])
        crop_mask = np.ascontiguousarray(mask[y1:y2, x1:x2])
        resized_bgr = cv2.resize(
            crop_rgb[:, :, ::-1],
            (512, 512),
            interpolation=cv2.INTER_AREA,
        )
        resized_mask = cv2.resize(
            (crop_mask > 0).astype(np.float32),
            (512, 512),
            interpolation=cv2.INTER_NEAREST,
        )
        image_tensor = np.ascontiguousarray(
            resized_bgr.transpose(2, 0, 1)[None].astype(np.float32) / 255.0
        )
        mask_tensor = np.ascontiguousarray(resized_mask[None, None])
        try:
            output = self._session.run(
                ["output"],
                {"image": image_tensor, "mask": mask_tensor},
            )[0]
        except Exception as error:
            raise InpainterError(f"LaMa inference failed: {error}") from error
        generated_bgr = np.asarray(output[0]).transpose(1, 2, 0)
        generated_rgb = np.clip(generated_bgr[:, :, ::-1], 0, 255).astype(np.uint8)
        generated_rgb = np.asarray(
            cv2.resize(
                generated_rgb,
                (crop_rgb.shape[1], crop_rgb.shape[0]),
                interpolation=cv2.INTER_CUBIC,
            ),
            dtype=np.uint8,
        )
        composed_crop = _feathered_composite(
            crop_rgb,
            generated_rgb,
            crop_mask,
            self._feather_radius,
        )
        result = image_rgb.copy()
        result[y1:y2, x1:x2] = composed_crop
        return result

    def inpaint(
        self,
        image_rgb: NDArray[np.uint8],
        mask: NDArray[np.uint8],
    ) -> NDArray[np.uint8]:
        if image_rgb.dtype != np.uint8 or image_rgb.ndim != 3:
            raise ValueError("image must be an HxWx3 uint8 array")
        if mask.dtype != np.uint8 or mask.shape != image_rgb.shape[:2]:
            raise ValueError("mask must be uint8 and match image dimensions")
        if not np.any(mask):
            return image_rgb.copy()

        regions = split_mask_regions(mask)
        if len(regions) <= 1:
            return self._inpaint_crop(image_rgb, mask)

        result = image_rgb.copy()
        for region in regions:
            result = self._inpaint_crop(result, region)
        return result
