from __future__ import annotations

import threading
import time
from pathlib import Path

import numpy as np
from PIL import Image

from app.core.job_store import JobStore
from app.desktop import BatchService, DesktopApi, frontend_directory
from app.domain.detection import BoundingBox, Detection
from app.domain.job import JobStatus
from app.domain.result import ProcessingResult


class FakeProcessor:
    def process(self, source: Path) -> ProcessingResult:
        return ProcessingResult(
            source.with_name(f"{source.stem}_clean{source.suffix}"),
            0.01,
            status=JobStatus.COMPLETED,
            detection_count=1,
        )


class BlockingProcessor(FakeProcessor):
    def __init__(self, entered: threading.Event, release: threading.Event) -> None:
        self._entered = entered
        self._release = release

    def process(self, source: Path) -> ProcessingResult:
        self._entered.set()
        assert self._release.wait(5)
        return super().process(source)


class FakeManualProcessor:
    def __init__(self, finished: threading.Event) -> None:
        self.finished = finished
        self.mask: np.ndarray | None = None

    def process(self, source: Path, mask: np.ndarray) -> ProcessingResult:
        self.mask = mask.copy()
        self.finished.set()
        return ProcessingResult(
            source.with_name(f"{source.stem}_reviewed{source.suffix}"),
            0.02,
            status=JobStatus.COMPLETED,
        )


def test_frontend_bundle_contains_only_local_assets() -> None:
    frontend = frontend_directory()

    assert (frontend / "index.html").is_file()
    assert (frontend / "styles.css").is_file()
    assert (frontend / "app.js").is_file()
    markup = (frontend / "index.html").read_text(encoding="utf-8")
    assert "https://" not in markup
    assert "http://" not in markup
    assert 'aria-label="拖放照片或文件夹"' in markup
    assert "Content-Security-Policy" in markup
    assert 'data-tool="rectangle"' in markup
    assert 'data-tool="brush_add"' in markup
    assert 'data-tool="brush_erase"' in markup
    assert "确认并重修" in markup
    stylesheet = (frontend / "styles.css").read_text(encoding="utf-8")
    assert "[hidden] { display: none !important; }" in stylesheet


def test_batch_service_processes_all_images_and_persists_results(tmp_path: Path) -> None:
    source_a = tmp_path / "a.jpg"
    source_b = tmp_path / "b.png"
    source_a.write_bytes(b"a")
    source_b.write_bytes(b"b")
    database = tmp_path / "jobs.sqlite3"
    events: list[tuple[str, dict[str, object]]] = []
    service = BatchService(
        lambda name, payload: events.append((name, payload)),
        lambda: FakeProcessor(),
        job_database=database,
    )

    assert service.start([tmp_path])
    assert not service.start([tmp_path])
    assert service.wait()

    names = [name for name, _payload in events]
    assert names[0] == "batch_accepted"
    assert names.count("item_started") == 2
    assert names.count("item_finished") == 2
    assert names[-1] == "batch_finished"
    with JobStore(database) as store:
        assert store.counts() == {"completed": 2}


def test_batch_service_rejects_controls_while_idle(tmp_path: Path) -> None:
    service = BatchService(
        lambda _name, _payload: None,
        lambda: FakeProcessor(),
        job_database=tmp_path / "jobs.sqlite3",
    )

    assert not service.pause()
    assert not service.resume()
    assert not service.cancel()


def test_cancel_preserves_current_result_and_cancels_remaining(tmp_path: Path) -> None:
    (tmp_path / "a.jpg").write_bytes(b"a")
    (tmp_path / "b.jpg").write_bytes(b"b")
    entered = threading.Event()
    release = threading.Event()
    database = tmp_path / "jobs.sqlite3"
    service = BatchService(
        lambda _name, _payload: None,
        lambda: BlockingProcessor(entered, release),
        job_database=database,
    )

    assert service.start([tmp_path])
    assert entered.wait(5)
    assert service.cancel()
    release.set()
    assert service.wait()

    with JobStore(database) as store:
        assert store.counts() == {"cancelled": 1, "completed": 1}


def test_desktop_api_exposes_no_public_object_graph() -> None:
    api = DesktopApi(lambda: FakeProcessor())

    assert all(name.startswith("_") for name in vars(api))


def test_desktop_review_round_trip_uses_persisted_detection(tmp_path: Path) -> None:
    source = tmp_path / "review.jpg"
    Image.new("RGB", (120, 80), "navy").save(source)
    database = tmp_path / "jobs.sqlite3"
    detection = Detection(BoundingBox(30, 30, 80, 45), 0.45)
    with JobStore(database) as store:
        identifier = store.create_job(source)
        store.record_result(
            identifier,
            ProcessingResult(
                None,
                0.1,
                status=JobStatus.REVIEW_REQUIRED,
                detection_count=1,
                detections=(detection,),
            ),
        )
    finished = threading.Event()
    manual = FakeManualProcessor(finished)
    api = DesktopApi(
        lambda: FakeProcessor(),
        lambda: manual,  # type: ignore[arg-type]
        job_database=database,
    )

    jobs = api.list_review_jobs()
    review = api.get_review_job(identifier)
    response = api.reprocess_review(
        identifier,
        [{"type": "rectangle", "start": [90, 20], "end": [110, 40]}],
    )

    assert jobs[0]["id"] == identifier
    assert str(review["image"]).startswith("data:image/jpeg;base64,")
    assert review["detections"][0]["confidence"] == 0.45  # type: ignore[index]
    assert response["accepted"] is True
    assert finished.wait(5)
    assert manual.mask is not None
    assert manual.mask[35, 100] == 255
    deadline = time.monotonic() + 5
    while True:
        with JobStore(database) as store:
            status = store.get_job(identifier).status
        if status is JobStatus.COMPLETED or time.monotonic() >= deadline:
            break
        time.sleep(0.01)
    assert status is JobStatus.COMPLETED
