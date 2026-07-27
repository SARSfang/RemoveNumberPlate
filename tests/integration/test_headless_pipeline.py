import hashlib
from pathlib import Path
from shutil import copy2

import pytest
from PIL import Image

from app.cli import build_processor
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
