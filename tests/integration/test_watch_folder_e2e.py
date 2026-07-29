"""End-to-end integration tests for the v0.3.0 watch-folder feature.

Exercises the real ``WatchFolderService`` (ctypes ``ReadDirectoryChangesW``)
and ``BatchService`` watch-queue continuation against the real Windows file
system — no ctypes mocking. Slow and Windows-only; run with
``pytest -m slow``.
"""

from __future__ import annotations

import shutil
import sys
import threading
import time
from pathlib import Path

import pytest
from PIL import Image

from app.core.job_store import JobStore
from app.core.watch_folder import WatchFolderService
from app.desktop import BatchService
from app.domain.job import JobStatus
from app.domain.result import ProcessingResult

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(
        not sys.platform.startswith("win"),
        reason="requires Windows ReadDirectoryChangesW",
    ),
]

_BATCH_TIMEOUT = 30.0
_WATCHER_READY_TIMEOUT = 5.0
# Small margin beyond the 1.5 s aggregator stability threshold and the
# _finish cleanup that clears _watch_pending after batch_finished.
_SETTLE_SECONDS = 0.3


# --------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------- #


class _RecordingSink:
    """Event sink that records events and signals batch/error completion.

    A ``threading.Event`` is set whenever a ``batch_finished`` or
    ``watch_folder_error`` event arrives; tests wait on it with a 30 s
    timeout (polling every 250 ms to re-check the batch counter).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.events: list[tuple[str, dict[str, object]]] = []
        self._batch_count = 0
        self._error_count = 0
        self.batch_finished = threading.Event()
        self.watch_folder_error = threading.Event()

    def __call__(self, name: str, payload: dict[str, object]) -> None:
        with self._lock:
            self.events.append((name, payload))
            if name == "batch_finished":
                self._batch_count += 1
            elif name == "watch_folder_error":
                self._error_count += 1
        if name == "batch_finished":
            self.batch_finished.set()
        elif name == "watch_folder_error":
            self.watch_folder_error.set()

    @property
    def batch_count(self) -> int:
        with self._lock:
            return self._batch_count

    def wait_for_batches(
        self,
        count: int,
        timeout: float = _BATCH_TIMEOUT,
    ) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.batch_count >= count:
                return True
            self.batch_finished.wait(timeout=0.25)
            self.batch_finished.clear()
        return self.batch_count >= count

    def wait_for_watch_error(self, timeout: float = _BATCH_TIMEOUT) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                if self._error_count > 0:
                    return True
            self.watch_folder_error.wait(timeout=0.25)
            self.watch_folder_error.clear()
        with self._lock:
            return self._error_count > 0


class FakeProcessor:
    """Writes a tiny real image to a directory OUTSIDE the watched tree.

    The output is deliberately placed outside the watch folder so the live
    ``ReadDirectoryChangesW`` watcher does not re-detect the freshly written
    file and create an enqueue loop (the watcher has no output-directory
    filter, unlike ``discover_images`` which skips ``车牌已消除``).
    """

    def __init__(self, output_root: Path) -> None:
        self._output_root = output_root

    def process(self, source: Path) -> ProcessingResult:
        output = self._output_root / f"{source.stem}_clean{source.suffix}"
        output.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (10, 10), "red").save(output)
        return ProcessingResult(
            output,
            0.01,
            status=JobStatus.COMPLETED,
            detection_count=1,
        )


def _write_image(path: Path, *, color: str = "blue", size: int = 32) -> None:
    """Create a minimal valid image at ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (size, size), color).save(path)


def _build_services(
    tmp_path: Path,
) -> tuple[WatchFolderService, BatchService, _RecordingSink, Path]:
    """Construct a wired WatchFolderService + BatchService pair.

    Returns ``(watch_service, batch_service, sink, output_root)`` where
    ``output_root`` is a sibling of the watch folder so processor outputs
    never trigger watcher events.
    """
    sink = _RecordingSink()
    database = tmp_path / "jobs.sqlite3"
    output_root = tmp_path / "outputs"
    output_root.mkdir(parents=True, exist_ok=True)
    batch_service = BatchService(
        sink,
        lambda: FakeProcessor(output_root),
        job_database=database,
    )
    watch_service = WatchFolderService(
        job_database=database,
        event_sink=sink,
    )
    watch_service.set_enqueue_callback(batch_service.enqueue_from_watch)
    return watch_service, batch_service, sink, output_root


def _wait_watcher_ready(
    watch_service: WatchFolderService,
    folder: Path,
    timeout: float = _WATCHER_READY_TIMEOUT,
) -> bool:
    """Wait until the watcher thread has opened its directory handle.

    The handle being published (``entry.handle != 0``) means CreateFileW
    succeeded and the thread is about to enter (or is already in) the
    ReadDirectoryChangesW loop, so file changes after this point are
    reliably captured.
    """
    key = str(folder.resolve())
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with watch_service._lock:  # noqa: SLF001 - integration test introspection
            entry = watch_service._folders.get(key)  # noqa: SLF001
            if (
                entry is not None
                and entry.watcher_thread is not None
                and entry.watcher_thread.is_alive()
                and entry.handle
            ):
                return True
        time.sleep(0.05)
    return False


# --------------------------------------------------------------------- #
# tests
# --------------------------------------------------------------------- #


def test_watch_folder_detects_new_file_and_processes(tmp_path: Path) -> None:
    """Watcher detects a new image; BatchService processes it end-to-end."""
    folder = tmp_path / "shoot"
    folder.mkdir()
    watch_service, batch_service, sink, output_root = _build_services(tmp_path)
    try:
        watch_service.add_folder(folder)
        watch_service.start()
        assert _wait_watcher_ready(watch_service, folder)
        time.sleep(_SETTLE_SECONDS)

        source = folder / "photo.jpg"
        _write_image(source)

        assert sink.wait_for_batches(1), "batch did not finish within timeout"
        assert not batch_service.busy
        assert (output_root / "photo_clean.jpg").is_file(), "output not generated"
    finally:
        watch_service.stop()


def test_watch_folder_redetects_modified_file(tmp_path: Path) -> None:
    """A completed file whose mtime/size changed is re-enqueued and reprocessed."""
    folder = tmp_path / "shoot"
    folder.mkdir()
    watch_service, batch_service, sink, output_root = _build_services(tmp_path)
    try:
        watch_service.add_folder(folder)
        watch_service.start()
        assert _wait_watcher_ready(watch_service, folder)
        time.sleep(_SETTLE_SECONDS)

        source = folder / "photo.jpg"
        _write_image(source, color="blue", size=32)

        assert sink.wait_for_batches(1), "first batch did not finish"
        # Let _finish clear _watch_pending so the modified file can re-enqueue.
        time.sleep(0.2)

        # Modify content AND size so dedup (mtime + size) flags it as changed.
        _write_image(source, color="green", size=64)

        assert sink.wait_for_batches(2), "second batch did not finish"
        assert sink.batch_count >= 2
        assert (output_root / "photo_clean.jpg").is_file()
        with JobStore(tmp_path / "jobs.sqlite3") as store:
            assert store.counts().get("completed", 0) >= 2
    finally:
        watch_service.stop()


def test_watch_folder_disables_on_deletion(tmp_path: Path) -> None:
    """Deleting a watched folder surfaces an error and auto-disables it."""
    folder = tmp_path / "shoot"
    folder.mkdir()
    watch_service, _batch_service, sink, _output_root = _build_services(tmp_path)
    try:
        watch_service.add_folder(folder)
        watch_service.start()
        assert _wait_watcher_ready(watch_service, folder)
        time.sleep(_SETTLE_SECONDS)

        # Delete the watched folder. On Windows the open watcher handle may
        # briefly block deletion; retry so delete-pending semantics settle.
        for _ in range(20):
            shutil.rmtree(folder, ignore_errors=True)
            if not folder.exists():
                break
            time.sleep(0.25)

        assert sink.wait_for_watch_error(timeout=15), (
            "watch_folder_error was not emitted after folder deletion"
        )

        states = watch_service.list_folder_states()
        assert len(states) == 1
        assert states[0]["error"] is not None
        assert states[0]["enabled"] is False
    finally:
        watch_service.stop()


def test_startup_rescan_recovers_unprocessed_files(tmp_path: Path) -> None:
    """Files present before startup are recovered by rescan_existing."""
    folder = tmp_path / "shoot"
    folder.mkdir()
    _write_image(folder / "a.jpg")
    _write_image(folder / "b.png")
    watch_service, batch_service, sink, output_root = _build_services(tmp_path)
    scan_cancel = threading.Event()
    try:
        watch_service.add_folder(folder)
        watch_service.start()

        collected = watch_service.rescan_existing(scan_cancel)
        assert len(collected) == 2
        assert not scan_cancel.is_set()

        count = batch_service.enqueue_from_watch(collected)
        assert count == 2

        assert sink.wait_for_batches(1), "batch did not finish within timeout"
        assert not batch_service.busy
        assert (output_root / "a_clean.jpg").is_file()
        assert (output_root / "b_clean.png").is_file()
    finally:
        watch_service.stop()


def test_cancel_watch_scan_keeps_already_collected(tmp_path: Path) -> None:
    """Cancelling the startup scan does not discard already-collected files.

    cancel_watch_scan stops future scanning; already-collected paths that
    are enqueued into BatchService are still processed to completion.
    """
    folder = tmp_path / "shoot"
    folder.mkdir()
    _write_image(folder / "a.jpg")
    _write_image(folder / "b.jpg")
    _write_image(folder / "c.jpg")
    watch_service, batch_service, sink, output_root = _build_services(tmp_path)
    scan_cancel = threading.Event()
    try:
        watch_service.add_folder(folder)
        watch_service.start()

        # The startup scan collects the pre-existing images.
        collected = watch_service.rescan_existing(scan_cancel)
        assert len(collected) == 3

        # Cancel the scan AFTER collection. Already-collected paths must
        # still be processed — cancel stops scanning, not the batch.
        scan_cancel.set()
        count = batch_service.enqueue_from_watch(collected)
        assert count == 3

        assert sink.wait_for_batches(1), "batch did not finish within timeout"
        assert not batch_service.busy
        for name in ("a_clean.jpg", "b_clean.jpg", "c_clean.jpg"):
            assert (output_root / name).is_file(), f"{name} not generated"
    finally:
        watch_service.stop()
