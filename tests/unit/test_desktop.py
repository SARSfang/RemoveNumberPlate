from __future__ import annotations

import threading
import time
from pathlib import Path

import numpy as np
from PIL import Image

from app import desktop
from app.core.job_store import JobStore
from app.desktop import BatchService, DesktopApi, frontend_directory
from app.domain.detection import BoundingBox, Detection
from app.domain.job import JobStatus
from app.domain.result import ProcessingResult
from app.release_readiness import ModelReadiness, StorageReadiness


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


class FailingProcessorFactory:
    def __call__(self) -> FakeProcessor:
        raise RuntimeError("model init failed")


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
    assert "connect-src 'none'" in markup
    assert 'data-tool="rectangle"' in markup
    assert 'data-tool="brush_add"' in markup
    assert 'data-tool="brush_erase"' in markup
    assert "确认并重修" in markup
    assert 'data-document="privacy"' in markup
    stylesheet = (frontend / "styles.css").read_text(encoding="utf-8")
    script = (frontend / "app.js").read_text(encoding="utf-8")
    assert "[hidden] { display: none !important; }" in stylesheet
    assert "database_recovered" in script
    assert "settings_recovered" in script


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
    assert names.index("batch_items_ready") < names.index("item_started")
    assert names.count("item_started") == 2
    assert names.count("item_finished") == 2
    assert names[-1] == "batch_finished"
    with JobStore(database) as store:
        assert store.counts() == {"completed": 2}


def test_batch_items_ready_is_ordered_and_does_not_expose_paths(tmp_path: Path) -> None:
    (tmp_path / "b.jpg").write_bytes(b"b")
    (tmp_path / "a.jpg").write_bytes(b"a")
    events: list[tuple[str, dict[str, object]]] = []
    service = BatchService(
        lambda name, payload: events.append((name, payload)),
        lambda: FakeProcessor(),
        job_database=tmp_path / "jobs.sqlite3",
    )

    assert service.start([tmp_path])
    assert service.wait()

    payload = next(value for name, value in events if name == "batch_items_ready")
    items = payload["items"]
    assert isinstance(items, list)
    assert [item["name"] for item in items] == ["a.jpg", "b.jpg"]
    assert [item["index"] for item in items] == [1, 2]
    assert all(item["status"] == "queued" for item in items)
    assert all("source" not in item for item in items)
    assert all(set(item) == {"job_id", "name", "index", "status"} for item in items)


def test_model_initialization_failure_marks_all_jobs_failed(tmp_path: Path) -> None:
    (tmp_path / "a.jpg").write_bytes(b"a")
    (tmp_path / "b.jpg").write_bytes(b"b")
    database = tmp_path / "jobs.sqlite3"
    events: list[tuple[str, dict[str, object]]] = []
    service = BatchService(
        lambda name, payload: events.append((name, payload)),
        FailingProcessorFactory(),
        job_database=database,
    )

    assert service.start([tmp_path])
    assert service.wait()

    names = [name for name, _payload in events]
    assert "batch_items_ready" in names
    assert "item_started" not in names
    assert names.count("item_finished") == 2
    assert any(
        name == "fatal_error" and "AI 引擎" in str(payload["message"])
        for name, payload in events
    )
    with JobStore(database) as store:
        assert store.counts() == {"failed": 2}


def test_batch_service_rejects_controls_while_idle(tmp_path: Path) -> None:
    service = BatchService(
        lambda _name, _payload: None,
        lambda: FakeProcessor(),
        job_database=tmp_path / "jobs.sqlite3",
    )

    assert not service.pause()
    assert not service.resume()
    assert not service.cancel()


def test_batch_service_stops_before_model_load_when_storage_is_low(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "source.jpg"
    source.write_bytes(b"source")
    events: list[tuple[str, dict[str, object]]] = []
    constructions = 0

    def factory() -> FakeProcessor:
        nonlocal constructions
        constructions += 1
        return FakeProcessor()

    monkeypatch.setattr(
        desktop,
        "inspect_storage",
        lambda _sources: StorageReadiness(False, 1, 0, "磁盘空间不足"),
    )
    service = BatchService(
        lambda name, payload: events.append((name, payload)),
        factory,
        job_database=tmp_path / "jobs.sqlite3",
    )

    assert service.start([source])
    assert service.wait()
    assert constructions == 0
    assert ("fatal_error", {"message": "磁盘空间不足"}) in events


def test_batch_service_reuses_model_session_across_batches(tmp_path: Path) -> None:
    source = tmp_path / "source.jpg"
    source.write_bytes(b"source")
    constructions = 0

    def factory() -> FakeProcessor:
        nonlocal constructions
        constructions += 1
        return FakeProcessor()

    service = BatchService(
        lambda _name, _payload: None,
        factory,
        job_database=tmp_path / "jobs.sqlite3",
    )

    assert service.start([source])
    assert service.wait()
    assert service.start([source])
    assert service.wait()
    assert constructions == 1


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


def test_desktop_api_exposes_no_public_object_graph(tmp_path: Path) -> None:
    api = DesktopApi(
        lambda: FakeProcessor(),
        job_database=tmp_path / "jobs.sqlite3",
    )

    assert all(name.startswith("_") for name in vars(api))


def test_desktop_api_rejects_batch_when_models_fail_integrity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "source.jpg"
    source.write_bytes(b"source")
    monkeypatch.setattr(
        desktop,
        "inspect_models",
        lambda _manifest, _models: ModelReadiness(False, (), "模型校验失败"),
    )
    api = DesktopApi(lambda: FakeProcessor(), job_database=tmp_path / "jobs.sqlite3")

    response = api.start_batch([str(source)])

    assert response == {"accepted": False, "message": "模型校验失败"}
    assert not api._service.busy


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


def test_history_can_queue_no_plate_for_manual_review(tmp_path: Path) -> None:
    source = tmp_path / "manual.jpg"
    source.write_bytes(b"image")
    database = tmp_path / "jobs.sqlite3"
    with JobStore(database) as store:
        identifier = store.create_job(source)
        store.record_result(
            identifier,
            ProcessingResult(None, 0.2, status=JobStatus.NO_PLATE),
        )
    api = DesktopApi(lambda: FakeProcessor(), job_database=database)

    history = api.list_history()
    response = api.queue_for_manual_review(identifier)

    assert history[0]["name"] == "manual.jpg"
    assert history[0]["elapsed"] == 0.2
    assert history[0]["source_available"] is True
    assert history[0]["output_available"] is False
    assert history[0]["detection_count"] == 0
    assert history[0]["risks"] == []
    assert "output" not in history[0]
    assert response["accepted"] is True
    with JobStore(database) as store:
        assert store.get_job(identifier).status is JobStatus.REVIEW_REQUIRED


def test_retry_job_requeues_existing_source(tmp_path: Path) -> None:
    source = tmp_path / "failed.jpg"
    source.write_bytes(b"image")
    database = tmp_path / "jobs.sqlite3"
    with JobStore(database) as store:
        identifier = store.create_job(source)
        store.record_result(
            identifier,
            ProcessingResult(
                None,
                0.1,
                status=JobStatus.FAILED,
                error="test failure",
            ),
        )
    api = DesktopApi(lambda: FakeProcessor(), job_database=database)

    response = api.retry_job(identifier)

    assert response["accepted"] is True
    assert api._service.wait()
    with JobStore(database) as store:
        assert store.counts() == {"completed": 1, "failed": 1}


def test_job_preview_bridge_uses_only_persisted_identifiers(tmp_path: Path) -> None:
    source = tmp_path / "photo.jpg"
    output = tmp_path / "车牌已消除" / "photo_clean.jpg"
    output.parent.mkdir()
    Image.new("RGB", (120, 80), "navy").save(source)
    Image.new("RGB", (120, 80), "black").save(output)
    database = tmp_path / "jobs.sqlite3"
    with JobStore(database) as store:
        identifier = store.create_job(source)
        store.record_result(
            identifier,
            ProcessingResult(output, 0.1, status=JobStatus.COMPLETED),
        )
    api = DesktopApi(lambda: FakeProcessor(), job_database=database)

    original = api.get_job_preview(identifier, "original")
    result = api.get_job_preview(identifier, "result")
    thumbnail = api.get_job_thumbnail(identifier)
    injected_path = api.get_job_preview(str(source), "original")

    assert original["available"] is True
    assert original["variant"] == "original"
    assert result["available"] is True
    assert result["variant"] == "result"
    assert thumbnail["available"] is True
    assert thumbnail["preview_width"] <= 320
    assert thumbnail["preview_height"] <= 220
    assert injected_path["available"] is False
    assert injected_path["reason"] == "unknown_job"
    assert str(tmp_path) not in str(original)
    assert str(tmp_path) not in str(result)


def test_job_preview_bridge_rejects_unknown_variant(tmp_path: Path) -> None:
    source = tmp_path / "photo.jpg"
    Image.new("RGB", (40, 30), "navy").save(source)
    database = tmp_path / "jobs.sqlite3"
    with JobStore(database) as store:
        identifier = store.create_job(source)
    api = DesktopApi(lambda: FakeProcessor(), job_database=database)

    response = api.get_job_preview(identifier, "..\\photo.jpg")

    assert response["available"] is False
    assert response["reason"] == "invalid_variant"


def test_open_job_output_resolves_from_database(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "photo.jpg"
    output = tmp_path / "车牌已消除" / "photo_clean.jpg"
    output.parent.mkdir()
    source.write_bytes(b"source")
    output.write_bytes(b"output")
    database = tmp_path / "jobs.sqlite3"
    with JobStore(database) as store:
        identifier = store.create_job(source)
        store.record_result(
            identifier,
            ProcessingResult(output, 0.1, status=JobStatus.COMPLETED),
        )
    opened: list[Path] = []
    monkeypatch.setattr(desktop.os, "startfile", lambda value: opened.append(Path(value)))
    api = DesktopApi(lambda: FakeProcessor(), job_database=database)

    assert api.open_job_output(identifier)
    assert opened == [output.parent]
    assert not api.open_job_output(str(output))
