from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from app.core.pipeline import ImageProcessor, ManualMaskProcessor
from app.domain.detection import BoundingBox, Detection
from app.domain.job import JobStatus, RiskReason


@dataclass
class StubDetector:
    detections: list[Detection]

    def detect(self, image_rgb: np.ndarray) -> list[Detection]:
        return self.detections


class StubInpainter:
    def inpaint(self, image_rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
        result = image_rgb.copy()
        result[mask > 0] = (1, 2, 3)
        return result


def _source(tmp_path: Path, name: str = "photo.png") -> Path:
    path = tmp_path / name
    Image.new("RGB", (400, 300), (20, 30, 40)).save(path)
    return path


def test_pipeline_writes_clean_output_without_touching_source(tmp_path: Path) -> None:
    source = _source(tmp_path)
    original = source.read_bytes()
    processor = ImageProcessor(
        StubDetector([Detection(BoundingBox(100, 150, 300, 210), 0.9)]),
        StubInpainter(),
    )

    result = processor.process(source)

    assert result.status is JobStatus.COMPLETED
    assert result.output is not None and result.output.name == "photo_clean.png"
    assert source.read_bytes() == original


def test_pipeline_skips_image_without_plate(tmp_path: Path) -> None:
    source = _source(tmp_path)
    result = ImageProcessor(StubDetector([]), StubInpainter()).process(source)
    assert result.status is JobStatus.NO_PLATE
    assert result.output is None


def test_pipeline_routes_low_confidence_to_review(tmp_path: Path) -> None:
    source = _source(tmp_path)
    processor = ImageProcessor(
        StubDetector([Detection(BoundingBox(100, 150, 300, 210), 0.4)]),
        StubInpainter(),
    )
    result = processor.process(source)
    assert result.status is JobStatus.REVIEW_REQUIRED
    assert RiskReason.LOW_CONFIDENCE in result.risks
    assert result.output is None


def test_manual_processor_can_render_to_cache_without_formal_output(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    cache = tmp_path / "adjustment-cache" / "preview.png"
    mask = np.zeros((300, 400), dtype=np.uint8)
    mask[100:120, 100:200] = 255

    result = ManualMaskProcessor(StubInpainter()).render_to(source, mask, cache)

    assert result.output == cache
    assert cache.is_file()
    assert not (tmp_path / "车牌已消除").exists()
