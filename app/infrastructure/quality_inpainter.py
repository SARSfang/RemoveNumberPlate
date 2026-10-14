"""Adaptive model routing with bounded texture transfer and traceable fallback."""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from app.core.repair_config import RepairConfig
from app.core.texture import enhance_texture
from app.infrastructure.lama_inpainter import (
    LamaInpainter,
    _context_bounds,
    _feathered_composite,
    split_mask_regions,
)
from app.infrastructure.migan_inpainter import InpainterError

LOGGER = logging.getLogger("remove_number_plate.repair")


class QualityInpainter:
    def __init__(self, models_dir: Path, config: RepairConfig) -> None:
        self.config = config
        self._models_dir = models_dir
        self._standard = LamaInpainter(models_dir / "inpainting_lama_2025jan.onnx")
        self._high: Any = None
        self.diagnostics: list[dict[str, object]] = []
        self.warnings: list[str] = []

    def _hd(self) -> Any:
        if self._high is None:
            from app.infrastructure.big_lama_inpainter import BigLamaInpainter
            self._high = BigLamaInpainter(self._models_dir)
        return self._high

    def inpaint(self, image_rgb: NDArray[np.uint8], mask: NDArray[np.uint8]) -> NDArray[np.uint8]:
        if image_rgb.dtype != np.uint8 or image_rgb.ndim != 3 or image_rgb.shape[2] != 3:
            raise ValueError("image must be HxWx3 uint8")
        if mask.dtype != np.uint8 or mask.shape != image_rgb.shape[:2]:
            raise ValueError("mask must be uint8 and match image dimensions")
        self.diagnostics = []
        self.warnings = []
        result = image_rgb.copy()
        for region in split_mask_regions(mask):
            started = time.perf_counter()
            # Start with tight context for large masks; preserve more context for tiny ones.
            bounds = _context_bounds(region, 2.0)
            if max(bounds[2]-bounds[0], bounds[3]-bounds[1]) < 256:
                bounds = _context_bounds(region, 4.0)
            x1, y1, x2, y2 = bounds
            crop = np.ascontiguousarray(image_rgb[y1:y2, x1:x2])
            selected = np.ascontiguousarray(region[y1:y2, x1:x2])
            wants_hd = self.config.quality == "high" or (
                self.config.quality == "auto" and max(crop.shape[:2]) > 512
            )
            model = "opencv-lama-512"
            fallback = ""
            if wants_hd:
                try:
                    generated = self._hd().generate_crop(crop, selected, self.config.hd_max_side)
                    model = "big-lama"
                except InpainterError as error:
                    if self.config.quality == "high":
                        raise
                    fallback = str(error)
                    warning = f"高清修复不可用，已使用标准模式：{fallback}"
                    if warning not in self.warnings:
                        self.warnings.append(warning)
                    generated = self._standard.generate_crop(crop, selected)
            else:
                generated = self._standard.generate_crop(crop, selected)
            texture = "disabled"
            if self.config.texture_enabled:
                generated, texture = enhance_texture(
                    crop, generated, selected, mask[y1:y2, x1:x2], self.config.texture_strength,
                )
            composed = _feathered_composite(crop, generated, selected, 6)
            result_crop = result[y1:y2, x1:x2]
            result_crop[selected > 0] = composed[selected > 0]
            limit = self.config.hd_max_side if model == "big-lama" else 512
            entry: dict[str, object] = {
                "model": model, "bounds": bounds,
                "scale": min(1.0, limit / max(crop.shape[:2])),
                "texture": texture, "fallback": fallback,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
            }
            self.diagnostics.append(entry)
            LOGGER.info("Repair region: %s", entry)
        return result
