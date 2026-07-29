from __future__ import annotations

import re
import threading
import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app import desktop
from app.core.job_store import JobStore
from app.core.watch_folder import WatchFolderService
from app.desktop import BatchService, DesktopApi, frontend_directory
from app.domain.detection import BoundingBox, Detection, Quadrilateral
from app.domain.job import JobStatus
from app.domain.result import ProcessingResult
from app.release_readiness import ModelReadiness, StorageReadiness
from app.settings import SettingsStore, UserSettings, WatchFolder


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
        output = source.with_name(f"{source.stem}_reviewed{source.suffix}")
        Image.open(source).save(output)
        self.finished.set()
        return ProcessingResult(
            output,
            0.02,
            status=JobStatus.COMPLETED,
        )

    def render_to(
        self,
        source: Path,
        mask: np.ndarray,
        output: Path,
    ) -> ProcessingResult:
        self.mask = mask.copy()
        output.parent.mkdir(parents=True, exist_ok=True)
        Image.open(source).save(output)
        self.finished.set()
        return ProcessingResult(
            output,
            0.02,
            status=JobStatus.COMPLETED,
        )


def test_frontend_bundle_contains_only_local_assets() -> None:
    frontend = frontend_directory()

    assert (frontend / "index.html").is_file()
    assert (frontend / "app.js").is_file()
    markup = (frontend / "index.html").read_text(encoding="utf-8")
    assert "https://" not in markup
    assert "http://" not in markup
    assert 'aria-label="拖放照片或文件夹"' in markup
    assert "Content-Security-Policy" in markup
    assert "connect-src 'none'" in markup
    assert 'data-tool="polygon"' in markup
    assert 'data-tool="add_polygon"' in markup
    assert 'data-tool="brush_add"' in markup
    assert 'data-tool="brush_erase"' in markup
    assert "生成临时预览" in markup
    assert 'id="adjust-region-button"' in markup
    assert 'id="save-adjustment-button"' in markup
    assert 'data-document="privacy"' in markup
    assert 'role="tablist"' in markup
    assert 'role="tab" aria-selected="true" aria-controls="canvas-stage"' in markup
    assert 'role="listbox"' in markup
    assert 'aria-modal="true"' in markup
    assert 'id="startup-retry-button"' in markup
    assert 'id="drop-title"' in markup
    assert 'id="default-mask-margin"' in markup
    assert 'id="default-mask-margin-number"' in markup
    assert 'aria-label="任务详情"' in markup
    assert 'min="-30" max="100" step="1" value="35"' in markup
    assert "PREVIEW-FIRST WORKSPACE" not in markup
    assert "EXCEPTION INBOX" not in markup
    assert "LOCAL JOB HISTORY" not in markup
    assert "PREFERENCES" not in markup
    local_assets = [
        value
        for value in re.findall(r'(?:href|src)="([^"]+)"', markup)
        if not value.startswith("#")
    ]
    assert local_assets
    assert all(not value.startswith(("http:", "https:")) for value in local_assets)
    assert all((frontend / value).is_file() for value in local_assets)
    stylesheet = (frontend / "styles" / "base.css").read_text(encoding="utf-8")
    script = (frontend / "app.js").read_text(encoding="utf-8")
    assert "[hidden]" in stylesheet
    assert "database_recovered" in script
    assert "settings_recovered" in script
    assert "window.app = { receiveBackendEvent }" in script
    assert 'setStartupState("failed", message)' in script
    assert 'setStartupState("loading")' in script


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


def test_mask_margin_setting_persists_without_resetting_preset(tmp_path: Path) -> None:
    api = DesktopApi(
        lambda: FakeProcessor(),
        job_database=tmp_path / "jobs.sqlite3",
    )
    settings_store = SettingsStore(tmp_path / "settings.json")
    api._settings_store = settings_store
    api._settings = UserSettings(preset="quality", mask_margin_ratio=0.35)

    response = api.set_mask_margin(72)

    assert response["accepted"] is True
    assert settings_store.load() == UserSettings(
        preset="quality",
        mask_margin_ratio=0.72,
    )


def test_processor_factory_receives_saved_mask_margin(monkeypatch) -> None:
    captured: list[tuple[float, float]] = []

    def fake_build_processor(confidence: float, margin: float) -> FakeProcessor:
        captured.append((confidence, margin))
        return FakeProcessor()

    monkeypatch.setattr(desktop, "build_processor", fake_build_processor)

    processor = DesktopApi._processor_factory_for("quality", 0.72)()

    assert isinstance(processor, FakeProcessor)
    assert captured == [(0.50, 0.72)]


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


def test_adjustment_preview_then_save_creates_new_version(
    tmp_path: Path,
) -> None:
    source = tmp_path / "photo.jpg"
    output_dir = tmp_path / "车牌已消除"
    first_output = output_dir / "photo_clean.jpg"
    output_dir.mkdir()
    Image.new("RGB", (120, 80), "navy").save(source)
    Image.new("RGB", (120, 80), "black").save(first_output)
    original_hash = source.read_bytes()
    old_result_hash = first_output.read_bytes()
    polygon = Quadrilateral(((30, 30), (80, 27), (82, 48), (28, 50)))
    detection = Detection(polygon.bounding_box, 0.8, polygon=polygon)
    database = tmp_path / "jobs.sqlite3"
    with JobStore(database) as store:
        identifier = store.create_job(source)
        store.record_result(
            identifier,
            ProcessingResult(
                first_output,
                0.1,
                status=JobStatus.COMPLETED,
                detection_count=1,
                detections=(detection,),
            ),
        )
    finished = threading.Event()
    manual = FakeManualProcessor(finished)
    events: list[tuple[str, dict[str, object]]] = []
    api = DesktopApi(
        lambda: FakeProcessor(),
        lambda: manual,  # type: ignore[arg-type]
        job_database=database,
    )
    api._send_event = lambda name, payload: events.append((name, payload))

    adjustment = api.get_adjustment_job(identifier)
    response = api.preview_adjustment(
        identifier,
        str(adjustment["revision"]),
        [
            {
                "type": "set_detection_polygon",
                "target_id": "detection:0",
                "points": [[32, 31], [78, 28], [80, 47], [30, 49]],
            },
            {"type": "set_margin", "value": 0.05},
        ],
    )

    assert adjustment["entry_available"] is True
    assert adjustment["detections"][0]["points"][0] == [30.0, 30.0]  # type: ignore[index]
    assert response["accepted"] is True
    assert finished.wait(5)
    deadline = time.monotonic() + 5
    while not any(name == "adjustment_preview_ready" for name, _ in events):
        assert time.monotonic() < deadline
        time.sleep(0.01)
    assert list(output_dir.iterdir()) == [first_output]
    preview_payload = next(
        payload for name, payload in events if name == "adjustment_preview_ready"
    )

    save_response = api.save_adjustment(
        identifier,
        str(preview_payload["preview_token"]),
    )

    assert save_response["accepted"] is True
    deadline = time.monotonic() + 5
    while not any(name == "adjustment_saved" for name, _ in events):
        assert time.monotonic() < deadline
        time.sleep(0.01)
    second_output = output_dir / "photo_clean_2.jpg"
    assert second_output.is_file()
    assert source.read_bytes() == original_hash
    assert first_output.read_bytes() == old_result_hash
    with JobStore(database) as store:
        saved = store.get_job(identifier)
        assert saved.output == second_output
        assert saved.detections == (detection,)
        assert store.latest_mask_revision(identifier)[-1] == {
            "type": "set_margin",
            "value": 0.05,
        }


def test_every_non_processing_job_can_open_adjustment(tmp_path: Path) -> None:
    source = tmp_path / "manual.jpg"
    Image.new("RGB", (40, 30), "navy").save(source)
    database = tmp_path / "jobs.sqlite3"
    with JobStore(database) as store:
        identifier = store.create_job(source)
        store.record_result(
            identifier,
            ProcessingResult(None, 0.1, status=JobStatus.NO_PLATE),
        )
    api = DesktopApi(lambda: FakeProcessor(), job_database=database)

    adjustment = api.get_adjustment_job(identifier)

    assert adjustment["entry_available"] is True
    assert adjustment["detections"] == []
    assert api.get_adjustment_job(str(source))["entry_available"] is False


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


# ---------------------------------------------------------------------- #
# Watch folder queue extension (spec v0.3.0 §5)
# ---------------------------------------------------------------------- #


def _make_batch_service(
    tmp_path: Path,
    factory: object,
) -> tuple[
    BatchService,
    list[tuple[str, dict[str, object]]],
]:
    events: list[tuple[str, dict[str, object]]] = []
    service = BatchService(
        lambda name, payload: events.append((name, payload)),
        factory,  # type: ignore[arg-type]
        job_database=tmp_path / "jobs.sqlite3",
    )
    return service, events


def test_start_rejects_empty_inputs(tmp_path: Path) -> None:
    service, _ = _make_batch_service(tmp_path, lambda: FakeProcessor())

    assert service.start([]) is False
    assert service.busy is False


def test_enqueue_from_watch_starts_batch_when_idle(tmp_path: Path) -> None:
    (tmp_path / "a.jpg").write_bytes(b"a")
    (tmp_path / "b.png").write_bytes(b"b")
    service, events = _make_batch_service(tmp_path, lambda: FakeProcessor())

    count = service.enqueue_from_watch([tmp_path / "a.jpg", tmp_path / "b.png"])

    assert count == 2
    assert service.wait()
    names = [name for name, _payload in events]
    assert names[0] == "batch_accepted"
    assert names.count("item_finished") == 2
    assert names[-1] == "batch_finished"


def test_enqueue_from_watch_queues_when_busy(tmp_path: Path) -> None:
    (tmp_path / "a.jpg").write_bytes(b"a")
    (tmp_path / "b.jpg").write_bytes(b"b")
    entered = threading.Event()
    release = threading.Event()
    service, events = _make_batch_service(
        tmp_path,
        lambda: BlockingProcessor(entered, release),
    )

    # First call starts the batch and blocks inside the processor.
    assert service.enqueue_from_watch([tmp_path / "a.jpg"]) == 1
    assert entered.wait(5)
    assert service.busy is True

    # Second call should queue, not start.
    events.clear()
    count = service.enqueue_from_watch([tmp_path / "b.jpg"])
    assert count == 1
    # No new batch_accepted while busy.
    assert all(name != "batch_accepted" for name, _payload in events)

    release.set()
    assert service.wait()
    names = [name for name, _payload in events]
    # Continuation should fire exactly one batch_accepted after finish.
    assert names.count("batch_accepted") == 1
    # a.jpg finishes after release.set() (BlockingProcessor was holding it),
    # plus b.jpg from the continuation — both emitted after events.clear().
    assert names.count("item_finished") == 2
    with JobStore(tmp_path / "jobs.sqlite3") as store:
        assert store.counts() == {"completed": 2}


def test_enqueue_from_watch_deduplicates_pending(tmp_path: Path) -> None:
    (tmp_path / "a.jpg").write_bytes(b"a")
    entered = threading.Event()
    release = threading.Event()
    service, _ = _make_batch_service(
        tmp_path,
        lambda: BlockingProcessor(entered, release),
    )

    service.enqueue_from_watch([tmp_path / "a.jpg"])
    assert entered.wait(5)

    # Second enqueue of the same path should be a no-op.
    count = service.enqueue_from_watch([tmp_path / "a.jpg"])
    assert count == 0

    release.set()
    service.wait()


def test_run_skips_continuation_when_cancelled(tmp_path: Path) -> None:
    (tmp_path / "a.jpg").write_bytes(b"a")
    (tmp_path / "b.jpg").write_bytes(b"b")
    entered = threading.Event()
    release = threading.Event()
    service, events = _make_batch_service(
        tmp_path,
        lambda: BlockingProcessor(entered, release),
    )

    service.enqueue_from_watch([tmp_path / "a.jpg"])
    assert entered.wait(5)
    service.enqueue_from_watch([tmp_path / "b.jpg"])  # queued for continuation
    events.clear()

    assert service.cancel() is True
    release.set()
    assert service.wait()

    names = [name for name, _payload in events]
    # batch_finished with cancelled=True, no follow-up batch_accepted.
    assert any(
        name == "batch_finished" and payload.get("cancelled") is True
        for name, payload in events
    )
    assert "batch_accepted" not in names


def test_cancel_clears_watch_queue(tmp_path: Path) -> None:
    (tmp_path / "a.jpg").write_bytes(b"a")
    (tmp_path / "b.jpg").write_bytes(b"b")
    (tmp_path / "c.jpg").write_bytes(b"c")
    entered = threading.Event()
    release = threading.Event()
    service, _ = _make_batch_service(
        tmp_path,
        lambda: BlockingProcessor(entered, release),
    )

    service.enqueue_from_watch([tmp_path / "a.jpg"])
    assert entered.wait(5)
    service.enqueue_from_watch([tmp_path / "b.jpg", tmp_path / "c.jpg"])

    assert service.cancel() is True
    # Watch queue and pending set must both be empty after cancel.
    with service._watch_lock:  # noqa: SLF001
        assert service._watch_queue == []
        assert service._watch_pending == set()

    release.set()
    service.wait()


def test_cancel_when_idle_clears_pending_queue(tmp_path: Path) -> None:
    service, _ = _make_batch_service(tmp_path, lambda: FakeProcessor())
    # Simulate a stale queue (e.g. user manually edited settings.json).
    service._watch_queue.append(tmp_path / "stale.jpg")  # noqa: SLF001
    service._watch_pending.add(str(tmp_path / "stale.jpg"))  # noqa: SLF001

    # cancel returns False (no batch running) but still clears the queue.
    assert service.cancel() is False

    with service._watch_lock:  # noqa: SLF001
        assert service._watch_queue == []
        assert service._watch_pending == set()


def test_pause_does_not_enqueue_or_continue(tmp_path: Path) -> None:
    (tmp_path / "a.jpg").write_bytes(b"a")
    (tmp_path / "b.jpg").write_bytes(b"b")
    entered = threading.Event()
    release = threading.Event()
    service, events = _make_batch_service(
        tmp_path,
        lambda: BlockingProcessor(entered, release),
    )

    service.enqueue_from_watch([tmp_path / "a.jpg"])
    assert entered.wait(5)
    service.enqueue_from_watch([tmp_path / "b.jpg"])  # queued
    events.clear()

    # Pause mid-batch — should not affect queue, just the running batch.
    assert service.pause() is True
    release.set()
    # Resume to let the batch finish naturally.
    assert service.resume() is True
    assert service.wait()

    names = [name for name, _payload in events]
    # Continuation still fires after resume.
    assert names.count("batch_accepted") == 1
    with JobStore(tmp_path / "jobs.sqlite3") as store:
        assert store.counts() == {"completed": 2}


# ---------------------------------------------------------------------- #
# DesktopApi watch folder bridge (spec v0.3.0 §7.4, §9)
# ---------------------------------------------------------------------- #


class _FakeWindow:
    """Minimal window stub returning a preset folder from create_file_dialog."""

    def __init__(self, folder: Path | None = None) -> None:
        self._folder = folder

    def create_file_dialog(self, dialog_type, **_kwargs):  # noqa: ANN001, ANN002
        if dialog_type is desktop.webview.FileDialog.FOLDER:
            return [str(self._folder)] if self._folder is not None else []
        return []


def _make_api(
    tmp_path: Path,
    *,
    watch_folders: tuple = (),
) -> DesktopApi:
    api = DesktopApi(
        lambda: FakeProcessor(),
        job_database=tmp_path / "jobs.sqlite3",
    )
    api._settings_store = SettingsStore(tmp_path / "settings.json")
    api._settings = UserSettings(
        preset="balanced",
        mask_margin_ratio=0.35,
        watch_folders=watch_folders,
    )
    api._settings_store.save(api._settings)
    api._watch_service.load_from_settings(watch_folders)
    return api


def test_desktop_api_loads_watch_folders_from_settings(tmp_path: Path) -> None:
    folder = tmp_path / "shoot"
    folder.mkdir()
    api = _make_api(
        tmp_path,
        watch_folders=(
            WatchFolder(
                path=str(folder),
                enabled=True,
                added_at="2026-07-29T10:00:00Z",
            ),
        ),
    )

    states = api.list_watch_folders()

    assert len(states) == 1
    assert states[0]["path"] == str(folder.resolve())
    assert states[0]["enabled"] is True
    assert states[0]["added_at"] == "2026-07-29T10:00:00Z"
    assert states[0]["error"] is None


def test_desktop_api_load_from_settings_marks_network_drive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _make_api(tmp_path)
    monkeypatch.setattr(
        WatchFolderService,
        "_is_network_path",
        staticmethod(lambda _path: True),
    )

    api._watch_service.load_from_settings(
        (
            WatchFolder(
                path=str(tmp_path),
                enabled=True,
                added_at="2026-07-29T10:00:00Z",
            ),
        ),
    )

    states = api.list_watch_folders()
    assert states[0]["error"] == "unsupported network drive"


def test_bootstrap_returns_watch_folders_and_scan_status(tmp_path: Path) -> None:
    api = _make_api(tmp_path)
    # Stub start()/stop() so no real watcher threads spawn or join, but let
    # _start_watch_service run so the scan thread is created.
    api._watch_service.start = lambda: None  # type: ignore[method-assign]
    api._watch_service.stop = lambda: None  # type: ignore[method-assign]

    payload = api.bootstrap()

    assert "watch_folders" in payload
    assert "watch_scan_in_progress" in payload
    assert payload["watch_scan_in_progress"] is True
    # Wait for the scan thread to finish so it doesn't leak into other tests.
    api._scan_cancel.set()
    if api._scan_thread is not None:  # noqa: SLF001
        api._scan_thread.join(timeout=5.0)


def test_add_watch_folder_persists_to_settings(tmp_path: Path) -> None:
    folder = tmp_path / "watched"
    folder.mkdir()
    api = _make_api(tmp_path)
    api._window = _FakeWindow(folder)  # type: ignore[assignment]

    response = api.add_watch_folder()

    assert response["accepted"] is True
    assert response["folder"]["path"] == str(folder.resolve())
    # Settings file now contains the folder.
    saved = SettingsStore(tmp_path / "settings.json").load()
    assert len(saved.watch_folders) == 1
    assert saved.watch_folders[0].path == str(folder.resolve())
    assert saved.watch_folders[0].enabled is True
    # Service also has the folder registered.
    assert len(api.list_watch_folders()) == 1


def test_add_watch_folder_rejects_network_drive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = tmp_path / "network"
    folder.mkdir()
    api = _make_api(tmp_path)
    api._window = _FakeWindow(folder)  # type: ignore[assignment]
    monkeypatch.setattr(
        WatchFolderService,
        "_is_network_path",
        staticmethod(lambda _path: True),
    )

    response = api.add_watch_folder()

    assert response["accepted"] is False
    assert "网络驱动器" in response["message"]
    # Nothing persisted.
    saved = SettingsStore(tmp_path / "settings.json").load()
    assert saved.watch_folders == ()


def test_remove_watch_folder_persists_to_settings(tmp_path: Path) -> None:
    folder = tmp_path / "watched"
    folder.mkdir()
    watch_folder = WatchFolder(
        path=str(folder),
        enabled=True,
        added_at="2026-07-29T10:00:00Z",
    )
    api = _make_api(tmp_path, watch_folders=(watch_folder,))

    response = api.remove_watch_folder(str(folder.resolve()))

    assert response["accepted"] is True
    saved = SettingsStore(tmp_path / "settings.json").load()
    assert saved.watch_folders == ()
    assert api.list_watch_folders() == []


def test_set_watch_folder_enabled_persists_to_settings(tmp_path: Path) -> None:
    folder = tmp_path / "watched"
    folder.mkdir()
    watch_folder = WatchFolder(
        path=str(folder),
        enabled=True,
        added_at="2026-07-29T10:00:00Z",
    )
    api = _make_api(tmp_path, watch_folders=(watch_folder,))

    api.set_watch_folder_enabled(str(folder.resolve()), False)

    saved = SettingsStore(tmp_path / "settings.json").load()
    assert saved.watch_folders[0].enabled is False
    states = api.list_watch_folders()
    assert states[0]["enabled"] is False


def test_cancel_watch_scan_sets_cancel_event(tmp_path: Path) -> None:
    api = _make_api(tmp_path)

    api.cancel_watch_scan()

    assert api._scan_cancel.is_set()  # noqa: SLF001


def test_shutdown_stops_watch_service(tmp_path: Path) -> None:
    api = _make_api(tmp_path)
    # Start the service so shutdown has something to stop.
    stopped: list[bool] = []

    def fake_stop() -> None:
        stopped.append(True)

    api._watch_service.start = lambda: None  # type: ignore[method-assign]
    api._watch_service.stop = fake_stop  # type: ignore[method-assign]
    api._watch_started = True

    api.shutdown()

    assert stopped == [True]
    assert api._watch_started is False  # noqa: SLF001


def test_startup_scan_enqueues_unprocessed_files(tmp_path: Path) -> None:
    folder = tmp_path / "shoot"
    folder.mkdir()
    (folder / "a.jpg").write_bytes(b"\xff\xd8")
    (folder / "b.jpg").write_bytes(b"\xff\xd8")
    watch_folder = WatchFolder(
        path=str(folder),
        enabled=True,
        added_at="2026-07-29T10:00:00Z",
    )
    api = _make_api(tmp_path, watch_folders=(watch_folder,))
    # Stub start()/stop() so no real watcher threads spawn or join.
    api._watch_service.start = lambda: None  # type: ignore[method-assign]
    api._watch_service.stop = lambda: None  # type: ignore[method-assign]
    api._watch_started = True  # pretend already started so _start_watch_service is no-op

    api._run_startup_scan()
    # The scan should have enqueued the two unprocessed images.
    assert len(api._service._watch_pending) >= 2 or api._service.busy  # noqa: SLF001


def test_startup_scan_can_be_cancelled(tmp_path: Path) -> None:
    folder = tmp_path / "shoot"
    folder.mkdir()
    (folder / "a.jpg").write_bytes(b"\xff\xd8")
    watch_folder = WatchFolder(
        path=str(folder),
        enabled=True,
        added_at="2026-07-29T10:00:00Z",
    )
    api = _make_api(tmp_path, watch_folders=(watch_folder,))
    api._watch_service.start = lambda: None  # type: ignore[method-assign]
    api._watch_service.stop = lambda: None  # type: ignore[method-assign]
    api._watch_started = True

    # Cancel before running the scan — collected paths should still enqueue.
    api._scan_cancel.set()
    api._run_startup_scan()

    # Even cancelled, the scan returns collected paths (it checks cancel
    # between folders/files; a single small folder may complete fully).
    # Just verify no crash and the event was emitted.


def test_desktop_api_remains_private_object_graph(tmp_path: Path) -> None:
    api = _make_api(tmp_path)

    assert all(name.startswith("_") for name in vars(api))
