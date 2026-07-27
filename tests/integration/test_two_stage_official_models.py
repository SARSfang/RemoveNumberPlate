from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.core.two_stage_detector import VehicleFirstPlateDetector
from app.infrastructure.paddle_plate_detector import PaddlePlateDetector
from app.infrastructure.paddle_vehicle_detector import PaddleVehicleDetector

ROOT = Path(__file__).parents[2]
VEHICLE_MODEL = ROOT / "models" / "PP-YOLOE-S_vehicle_infer"
PLATE_MODEL = ROOT / "models" / "ch_PP-OCRv3_det_infer"
SAMPLE_IMAGE = ROOT / "testdata" / "public" / "ppvehicleplate.jpg"


@pytest.mark.model
def test_official_two_stage_models_detect_sample_plate() -> None:
    if not all(path.exists() for path in (VEHICLE_MODEL, PLATE_MODEL, SAMPLE_IMAGE)):
        pytest.skip("official models or sample image are not installed")
    pytest.importorskip("paddle")
    image = np.asarray(Image.open(SAMPLE_IMAGE).convert("RGB"))
    pipeline = VehicleFirstPlateDetector(
        PaddleVehicleDetector(VEHICLE_MODEL, use_gpu=True),
        PaddlePlateDetector(
            PLATE_MODEL,
            use_gpu=True,
            limit_side_len=736,
            limit_type="min",
        ),
    )

    detections = pipeline.detect(image)

    assert detections
    assert max(detection.confidence for detection in detections) >= 0.75
