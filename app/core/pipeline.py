"""Single-image license-plate removal pipeline."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from app.core.detector import Detector
from app.core.image_io import allocate_output_path, load_image, write_image_atomic
from app.core.inpainter import Inpainter
from app.core.mask_builder import (
    DEFAULT_PLATE_MASK_POLICY,
    PlateMaskPolicy,
    build_plate_mask,
)
from app.core.risk_gate import assess_detection_risks
from app.domain.job import JobStatus
from app.domain.result import ProcessingResult


class ImageProcessor:
    """Coordinate pure model adapters and metadata-safe image I/O."""

    def __init__(
        self,
        detector: Detector,
        inpainter: Inpainter,
        *,
        auto_confidence: float = 0.60,
        mask_policy: PlateMaskPolicy = DEFAULT_PLATE_MASK_POLICY,
    ) -> None:
        if not 0 <= auto_confidence <= 1:
            raise ValueError("auto_confidence must be between 0 and 1")
        self._detector = detector
        self._inpainter = inpainter
        self._auto_confidence = auto_confidence
        self._mask_policy = mask_policy

    def process(self, source: Path) -> ProcessingResult:
        start = time.perf_counter()
        loaded = load_image(source)
        image_shape = (
            int(loaded.pixels_rgb.shape[0]),
            int(loaded.pixels_rgb.shape[1]),
        )
        detections = self._detector.detect(loaded.pixels_rgb)
        if not detections:
            return ProcessingResult(
                None,
                time.perf_counter() - start,
                status=JobStatus.NO_PLATE,
            )

        risks = assess_detection_risks(
            image_shape,
            detections,
            auto_confidence=self._auto_confidence,
        )
        if risks:
            return ProcessingResult(
                None,
                time.perf_counter() - start,
                risks=risks,
                status=JobStatus.REVIEW_REQUIRED,
                detection_count=len(detections),
                detections=tuple(detections),
            )

        mask = build_plate_mask(image_shape, detections, self._mask_policy)
        result_pixels = self._inpainter.inpaint(loaded.pixels_rgb, mask)
        while True:
            output = allocate_output_path(source)
            try:
                write_image_atomic(loaded, result_pixels, output)
                break
            except FileExistsError:
                continue
        return ProcessingResult(
            output,
            time.perf_counter() - start,
            status=JobStatus.COMPLETED,
            detection_count=len(detections),
            detections=tuple(detections),
        )


class ManualMaskProcessor:
    """Apply a user-confirmed full-resolution mask without re-running detection."""

    def __init__(self, inpainter: Inpainter) -> None:
        self._inpainter = inpainter

    def process(
        self,
        source: Path,
        mask: NDArray[np.uint8],
    ) -> ProcessingResult:
        start = time.perf_counter()
        loaded = load_image(source)
        if mask.shape != loaded.pixels_rgb.shape[:2]:
            raise ValueError("manual mask size must match the orientation-normalized image")
        result_pixels = self._inpainter.inpaint(loaded.pixels_rgb, mask)
        while True:
            output = allocate_output_path(source)
            try:
                write_image_atomic(loaded, result_pixels, output)
                break
            except FileExistsError:
                continue
        return ProcessingResult(
            output,
            time.perf_counter() - start,
            status=JobStatus.COMPLETED,
        )
