"""Detector interface implemented by the selected M1 runtime."""

from __future__ import annotations

from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from app.domain.detection import Detection


class Detector(Protocol):
    def detect(self, image_rgb: NDArray[np.uint8]) -> list[Detection]:
        """Return detections in source-image pixel coordinates."""
        ...
