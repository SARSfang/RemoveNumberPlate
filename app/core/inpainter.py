"""Inpainting interface implemented by the selected M1 runtime."""

from __future__ import annotations

from typing import Protocol

import numpy as np
from numpy.typing import NDArray


class Inpainter(Protocol):
    def inpaint(
        self,
        image_rgb: NDArray[np.uint8],
        mask: NDArray[np.uint8],
    ) -> NDArray[np.uint8]:
        """Replace pixels selected by a binary mask."""
        ...
