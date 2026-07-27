from pathlib import Path

import numpy as np
import pytest

from app.infrastructure.lama_inpainter import LamaInpainter

MODEL_PATH = Path(__file__).parents[2] / "models" / "inpainting_lama_2025jan.onnx"


@pytest.mark.model
def test_lama_inpaints_mask_and_preserves_far_pixels() -> None:
    if not MODEL_PATH.is_file():
        pytest.skip("official OpenCV LaMa model is not installed")
    pytest.importorskip("onnxruntime")
    image = np.full((512, 768, 3), (30, 50, 80), dtype=np.uint8)
    image[220:290, 280:490] = (210, 140, 60)
    mask = np.zeros(image.shape[:2], dtype=np.uint8)
    mask[215:295, 270:500] = 255
    inpainter = LamaInpainter(MODEL_PATH)

    result = inpainter.inpaint(image, mask)

    assert result.shape == image.shape
    assert result.dtype == np.uint8
    np.testing.assert_array_equal(result[:100], image[:100])
    assert np.any(result[mask > 0] != image[mask > 0])
