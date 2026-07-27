from pathlib import Path

import numpy as np
import pytest

from app.infrastructure.migan_inpainter import MiganInpainter

MODEL_PATH = Path(__file__).parents[2] / "models" / "migan_pipeline_v2.onnx"


@pytest.mark.model
def test_migan_inpaints_mask_and_preserves_unmasked_pixels() -> None:
    if not MODEL_PATH.is_file():
        pytest.skip("official MI-GAN model is not installed")
    pytest.importorskip("onnxruntime")
    image = np.zeros((256, 256, 3), dtype=np.uint8)
    image[:, :128] = (40, 80, 120)
    image[:, 128:] = (120, 80, 40)
    mask = np.zeros((256, 256), dtype=np.uint8)
    mask[96:160, 96:160] = 255
    inpainter = MiganInpainter(MODEL_PATH, use_gpu=True)

    result = inpainter.inpaint(image, mask)

    assert result.shape == image.shape
    assert result.dtype == np.uint8
    np.testing.assert_array_equal(result[mask == 0], image[mask == 0])
    assert np.any(result[mask > 0] != image[mask > 0])
