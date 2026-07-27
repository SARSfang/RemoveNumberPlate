import hashlib
from pathlib import Path
from shutil import copy2

import numpy as np
import pytest
from PIL import Image

from app.cli import build_manual_processor, build_processor
from app.core.image_io import load_image
from app.domain.job import JobStatus

ROOT = Path(__file__).parents[2]
SAMPLE = ROOT / "testdata" / "public" / "ppvehicleplate.jpg"


@pytest.mark.model
def test_real_headless_pipeline_writes_verified_clean_output(tmp_path: Path) -> None:
    required = (
        ROOT / "models" / "PP-YOLOE-S_vehicle_infer",
        ROOT / "models" / "ch_PP-OCRv3_det_infer",
        ROOT / "models" / "inpainting_lama_2025jan.onnx",
        SAMPLE,
    )
    if not all(path.exists() for path in required):
        pytest.skip("official models or sample image are not installed")
    source = tmp_path / "sample.jpg"
    copy2(SAMPLE, source)
    original_digest = hashlib.sha256(source.read_bytes()).hexdigest()

    result = build_processor(0.60).process(source)

    assert result.status is JobStatus.COMPLETED
    assert result.output is not None and result.output.name == "sample_clean.jpg"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original_digest
    with Image.open(result.output) as output:
        output.verify()


@pytest.mark.model
def test_real_manual_review_pipeline_writes_verified_output(tmp_path: Path) -> None:
    required = (
        ROOT / "models" / "inpainting_lama_2025jan.onnx",
        SAMPLE,
    )
    if not all(path.exists() for path in required):
        pytest.skip("official inpainting model or sample image is not installed")
    source = tmp_path / "manual.jpg"
    copy2(SAMPLE, source)
    original_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    loaded = load_image(source)
    height, width = loaded.pixels_rgb.shape[:2]
    mask = np.zeros((height, width), dtype=np.uint8)
    center_x, center_y = width // 2, height // 2
    mask[center_y - 20 : center_y + 20, center_x - 60 : center_x + 60] = 255

    result = build_manual_processor().process(source, mask)

    assert result.status is JobStatus.COMPLETED
    assert result.output is not None and result.output.name == "manual_clean.jpg"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original_digest
    with Image.open(result.output) as output:
        output.verify()
