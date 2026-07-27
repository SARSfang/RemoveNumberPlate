from pathlib import Path

import numpy as np
import pytest

from app.infrastructure.paddle_plate_detector import PaddlePlateDetector

MODEL_DIR = Path(__file__).parents[2] / "models" / "ch_PP-OCRv3_det_infer"


@pytest.mark.model
def test_official_paddle_detector_runs_on_blank_image() -> None:
    if not MODEL_DIR.is_dir():
        pytest.skip("official Paddle model is not installed")
    pytest.importorskip("paddle")
    detector = PaddlePlateDetector(MODEL_DIR, use_gpu=True, limit_side_len=640)
    image = np.zeros((480, 640, 3), dtype=np.uint8)

    detections = detector.detect(image)

    assert detections == []
