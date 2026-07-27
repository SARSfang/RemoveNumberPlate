from pathlib import Path

from PIL import Image

from app.core.batch import process_batch
from app.domain.job import JobStatus
from app.domain.result import ProcessingResult


class FailingSecondProcessor:
    def process(self, source: Path) -> ProcessingResult:
        if source.name == "b.png":
            raise RuntimeError("injected failure")
        return ProcessingResult(None, 0, status=JobStatus.NO_PLATE)


def test_batch_isolates_single_image_failure(tmp_path: Path) -> None:
    for name in ("a.png", "b.png", "c.png"):
        Image.new("RGB", (4, 4)).save(tmp_path / name)

    report = process_batch([tmp_path], FailingSecondProcessor())

    assert report.count(JobStatus.NO_PLATE) == 2
    assert report.count(JobStatus.FAILED) == 1
    assert report.items[2].source.name == "c.png"
