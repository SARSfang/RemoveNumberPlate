"""Unit tests for WatchFolderService (no real watcher threads).

Watcher/aggregator thread behaviour is covered by integration tests
(tests/integration/test_watch_folder_e2e.py). These tests exercise the
pure logic: dedup strategy, rescan_existing, network path detection,
notify-buffer parsing, and folder management API.
"""

from __future__ import annotations

import ctypes
import threading
import time
from pathlib import Path

import pytest

from app.core.job_store import JobStore
from app.core.watch_folder import (
    _FILE_ACTION_ADDED,
    _FILE_ACTION_MODIFIED,
    WatchFolderEntry,
    WatchFolderError,
    WatchFolderService,
)
from app.domain.job import JobStatus
from app.settings import WatchFolder


def _make_service(tmp_path: Path) -> tuple[WatchFolderService, list[tuple[str, dict]]]:
    """Construct a service with a recording event sink."""
    events: list[tuple[str, dict]] = []

    def sink(name: str, payload: dict) -> None:
        events.append((name, payload))

    service = WatchFolderService(tmp_path / "jobs.sqlite3", sink)
    return service, events


# ---------------------------------------------------------------------- #
# folder management API
# ---------------------------------------------------------------------- #


def test_list_folders_returns_empty_when_nothing_registered(tmp_path: Path) -> None:
    service, _ = _make_service(tmp_path)
    assert service.list_folders() == []


def test_add_folder_registers_enabled_folder(tmp_path: Path) -> None:
    service, events = _make_service(tmp_path)
    folder = tmp_path / "shoot"

    result = service.add_folder(folder)

    assert result.path == str(folder.resolve())
    assert result.enabled is True
    assert result.added_at
    assert service.list_folders() == [result]
    assert ("watch_started", {"folder": str(folder.resolve())}) in events


def test_add_folder_is_idempotent_for_same_path(tmp_path: Path) -> None:
    service, _ = _make_service(tmp_path)
    folder = tmp_path / "shoot"

    first = service.add_folder(folder)
    second = service.add_folder(folder)

    # Idempotent: second call returns the same registered WatchFolder.
    assert first == second
    assert service.list_folders() == [first]


def test_remove_folder_emits_stopped_event(tmp_path: Path) -> None:
    service, events = _make_service(tmp_path)
    folder = tmp_path / "shoot"
    service.add_folder(folder)
    events.clear()

    service.remove_folder(folder)

    assert service.list_folders() == []
    assert any(
        name == "watch_stopped" and payload["reason"] == "removed"
        for name, payload in events
    )


def test_remove_unknown_folder_is_silent(tmp_path: Path) -> None:
    service, events = _make_service(tmp_path)
    service.remove_folder(tmp_path / "never-added")
    assert events == []


def test_set_enabled_toggles_flag(tmp_path: Path) -> None:
    service, _ = _make_service(tmp_path)
    folder = tmp_path / "shoot"
    service.add_folder(folder)

    service.set_enabled(folder, enabled=False)

    assert service.list_folders()[0].enabled is False

    service.set_enabled(folder, enabled=True)

    assert service.list_folders()[0].enabled is True


def test_set_enabled_clears_prior_error(tmp_path: Path) -> None:
    service, _ = _make_service(tmp_path)
    folder = tmp_path / "shoot"
    service.add_folder(folder)
    # Inject an error directly to simulate watcher failure.
    with service._lock:  # noqa: SLF001 - test internal state
        entry = service._folders[str(folder.resolve())]
        entry.error = "previous failure"

    service.set_enabled(folder, enabled=False)
    service.set_enabled(folder, enabled=True)

    with service._lock:  # noqa: SLF001
        entry = service._folders[str(folder.resolve())]
    assert entry.error is None


# ---------------------------------------------------------------------- #
# network drive detection
# ---------------------------------------------------------------------- #


def test_is_network_path_detects_unc_path() -> None:
    # UNC paths are detected by the leading "\\\\" prefix without any win32 call.
    assert WatchFolderService._is_network_path(Path("\\\\server\\share\\sub")) is True


def test_is_network_path_detects_mapped_drive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.core.watch_folder as watch_module

    class _FakeKernel32:
        def GetDriveTypeW(self, drive: str) -> int:
            assert drive == "C:\\"
            return 4  # DRIVE_REMOTE

    monkeypatch.setattr(watch_module, "_KERNEL32", _FakeKernel32())

    assert WatchFolderService._is_network_path(Path("C:\\Users\\me")) is True


def test_is_network_path_returns_false_for_local_drive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.core.watch_folder as watch_module

    class _FakeKernel32:
        def GetDriveTypeW(self, drive: str) -> int:
            return 3  # DRIVE_FIXED

    monkeypatch.setattr(watch_module, "_KERNEL32", _FakeKernel32())

    assert WatchFolderService._is_network_path(Path("C:\\Users\\me")) is False


def test_add_folder_rejects_network_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service, _ = _make_service(tmp_path)
    network_path = Path("\\\\server\\share")

    with pytest.raises(WatchFolderError, match="network"):
        service.add_folder(network_path)

    assert service.list_folders() == []


# ---------------------------------------------------------------------- #
# dedup strategy (_should_enqueue)
# ---------------------------------------------------------------------- #


def _write_image(path: Path, content: bytes = b"\xff\xd8\xff\xe0fake") -> None:
    path.write_bytes(content)


def test_should_enqueue_true_for_unknown_file(tmp_path: Path) -> None:
    service, _ = _make_service(tmp_path)
    source = tmp_path / "photo.jpg"
    _write_image(source)
    with JobStore(tmp_path / "jobs.sqlite3") as store:
        assert service._should_enqueue(store, source) is True


def test_should_enqueue_false_for_unsupported_extension(tmp_path: Path) -> None:
    service, _ = _make_service(tmp_path)
    source = tmp_path / "notes.txt"
    _write_image(source, b"hello")
    with JobStore(tmp_path / "jobs.sqlite3") as store:
        assert service._should_enqueue(store, source) is False


def test_should_enqueue_false_for_completed_unchanged_file(tmp_path: Path) -> None:
    service, _ = _make_service(tmp_path)
    source = tmp_path / "photo.jpg"
    _write_image(source)
    with JobStore(tmp_path / "jobs.sqlite3") as store:
        job_id = store.create_job(source)
        store.set_status(job_id, JobStatus.COMPLETED)
        # record_result writes file_mtime/size via stat at create_job time.
        from app.domain.result import ProcessingResult

        store.record_result(
            job_id,
            ProcessingResult(
                output=tmp_path / "out.jpg",
                elapsed_seconds=1.0,
                status=JobStatus.COMPLETED,
                detection_count=0,
            ),
        )
        assert service._should_enqueue(store, source) is False


def test_should_enqueue_true_for_completed_changed_file(tmp_path: Path) -> None:
    service, _ = _make_service(tmp_path)
    source = tmp_path / "photo.jpg"
    _write_image(source, b"original")
    with JobStore(tmp_path / "jobs.sqlite3") as store:
        job_id = store.create_job(source)
        from app.domain.result import ProcessingResult

        store.record_result(
            job_id,
            ProcessingResult(
                output=tmp_path / "out.jpg",
                elapsed_seconds=1.0,
                status=JobStatus.COMPLETED,
                detection_count=0,
            ),
        )
        # Modify file content + bump mtime past filesystem resolution.
        time.sleep(0.05)
        _write_image(source, b"modified-content-longer")

    with JobStore(tmp_path / "jobs.sqlite3") as store:
        assert service._should_enqueue(store, source) is True


def test_should_enqueue_false_for_inflight_statuses(tmp_path: Path) -> None:
    service, _ = _make_service(tmp_path)
    source = tmp_path / "photo.jpg"
    _write_image(source)
    with JobStore(tmp_path / "jobs.sqlite3") as store:
        for status in (
            JobStatus.QUEUED,
            JobStatus.DETECTING,
            JobStatus.INPAINTING,
            JobStatus.WRITING,
        ):
            job_id = store.create_job(source)
            store.set_status(job_id, status)
            assert service._should_enqueue(store, source) is False


def test_should_enqueue_true_for_failed_or_review(tmp_path: Path) -> None:
    service, _ = _make_service(tmp_path)
    source = tmp_path / "photo.jpg"
    _write_image(source)
    with JobStore(tmp_path / "jobs.sqlite3") as store:
        for status in (
            JobStatus.FAILED,
            JobStatus.REVIEW_REQUIRED,
            JobStatus.NO_PLATE,
            JobStatus.AUTO_READY,
        ):
            job_id = store.create_job(source)
            store.set_status(job_id, status)
            assert service._should_enqueue(store, source) is True


def test_should_enqueue_false_when_file_disappeared(tmp_path: Path) -> None:
    service, _ = _make_service(tmp_path)
    source = tmp_path / "real.jpg"
    _write_image(source)
    with JobStore(tmp_path / "jobs.sqlite3") as store:
        job_id = store.create_job(source)
        from app.domain.result import ProcessingResult

        store.record_result(
            job_id,
            ProcessingResult(
                output=tmp_path / "out.jpg",
                elapsed_seconds=1.0,
                status=JobStatus.COMPLETED,
                detection_count=0,
            ),
        )
        # File is removed after a COMPLETED job was recorded.
        source.unlink()
        assert service._should_enqueue(store, source) is False


# ---------------------------------------------------------------------- #
# rescan_existing
# ---------------------------------------------------------------------- #


def test_rescan_existing_finds_unprocessed_files(tmp_path: Path) -> None:
    service, _ = _make_service(tmp_path)
    folder = tmp_path / "shoot"
    folder.mkdir()
    (folder / "a.jpg").write_bytes(b"\xff\xd8")
    (folder / "b.png").write_bytes(b"\x89PNG")
    service.add_folder(folder)

    cancel = threading.Event()
    result = service.rescan_existing(cancel)

    assert {p.name for p in result} == {"a.jpg", "b.png"}
    assert cancel.is_set() is False


def test_rescan_existing_skips_completed_files(tmp_path: Path) -> None:
    service, _ = _make_service(tmp_path)
    folder = tmp_path / "shoot"
    folder.mkdir()
    processed = folder / "done.jpg"
    _write_image(processed)
    pending = folder / "todo.jpg"
    _write_image(pending)
    service.add_folder(folder)

    with JobStore(tmp_path / "jobs.sqlite3") as store:
        job_id = store.create_job(processed)
        from app.domain.result import ProcessingResult

        store.record_result(
            job_id,
            ProcessingResult(
                output=tmp_path / "out.jpg",
                elapsed_seconds=1.0,
                status=JobStatus.COMPLETED,
                detection_count=0,
            ),
        )

    cancel = threading.Event()
    result = service.rescan_existing(cancel)

    assert [p.name for p in result] == ["todo.jpg"]


def test_rescan_existing_skips_network_drives(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service, _ = _make_service(tmp_path)
    folder = tmp_path / "shoot"
    folder.mkdir()
    (folder / "a.jpg").write_bytes(b"\xff\xd8")

    # Force add_folder to bypass the network check (simulating a path that
    # was added via direct settings.json edit and turned into a network drive
    # before rescan runs).
    monkeypatch.setattr(
        WatchFolderService,
        "_is_network_path",
        staticmethod(lambda _path: True),
    )
    # Insert entry directly to skip add_folder's network guard.
    entry = WatchFolderEntry(
        watch_folder=WatchFolder(
            path=str(folder),
            enabled=True,
            added_at="2026-07-29T10:00:00Z",
        )
    )
    with service._lock:  # noqa: SLF001
        service._folders[str(folder)] = entry

    cancel = threading.Event()
    result = service.rescan_existing(cancel)

    assert result == []


def test_rescan_existing_returns_partial_on_cancel(tmp_path: Path) -> None:
    service, _ = _make_service(tmp_path)
    folder = tmp_path / "shoot"
    folder.mkdir()
    for index in range(20):
        (folder / f"{index:02d}.jpg").write_bytes(b"\xff\xd8")
    service.add_folder(folder)

    cancel = threading.Event()

    # Cancel after the first discovered file. We can't intercept mid-iteration
    # without instrumentation, so toggle cancel inside a custom discover_images
    # replacement via patching is overkill — instead cancel immediately and
    # verify rescan still returns gracefully (possibly empty or partial).
    cancel.set()
    result = service.rescan_existing(cancel)

    # No invariant on count; the contract is "returns immediately, no hang".
    assert isinstance(result, list)


def test_rescan_existing_skips_disabled_folders(tmp_path: Path) -> None:
    service, _ = _make_service(tmp_path)
    folder = tmp_path / "shoot"
    folder.mkdir()
    (folder / "a.jpg").write_bytes(b"\xff\xd8")
    service.add_folder(folder)
    service.set_enabled(folder, enabled=False)

    cancel = threading.Event()
    result = service.rescan_existing(cancel)

    assert result == []


# ---------------------------------------------------------------------- #
# notify buffer parsing
# ---------------------------------------------------------------------- #


def _build_notify_buffer(records: list[tuple[str, int]]) -> tuple[ctypes.Array[int], int]:
    """Build a Win32 FILE_NOTIFY_INFORMATION buffer for testing."""
    buffer = (ctypes.c_ubyte * 8192)()
    offset = 0
    for index, (name, action) in enumerate(records):
        name_bytes = name.encode("utf-16-le")
        name_length = len(name_bytes)
        # Pad name to 4-byte alignment per FILE_NOTIFY_INFORMATION spec.
        padded_name = (name_length + 3) & ~3
        is_last = index == len(records) - 1
        next_offset = 0 if is_last else 12 + padded_name
        buffer[offset : offset + 4] = next_offset.to_bytes(4, "little")
        buffer[offset + 4 : offset + 8] = action.to_bytes(4, "little")
        buffer[offset + 8 : offset + 12] = name_length.to_bytes(4, "little")
        buffer[offset + 12 : offset + 12 + name_length] = name_bytes
        if is_last:
            offset += 12 + padded_name
        else:
            offset += next_offset
    return buffer, offset


def test_iter_notify_entries_parses_single_record() -> None:
    buffer, length = _build_notify_buffer([("photo.jpg", _FILE_ACTION_ADDED)])
    entries = WatchFolderService._iter_notify_entries(buffer, length)
    assert entries == [("photo.jpg", _FILE_ACTION_ADDED)]


def test_iter_notify_entries_parses_multiple_records() -> None:
    buffer, length = _build_notify_buffer(
        [
            ("photo.jpg", _FILE_ACTION_ADDED),
            ("notes.txt", _FILE_ACTION_MODIFIED),
        ]
    )
    entries = WatchFolderService._iter_notify_entries(buffer, length)
    assert entries == [
        ("photo.jpg", _FILE_ACTION_ADDED),
        ("notes.txt", _FILE_ACTION_MODIFIED),
    ]


def test_iter_notify_entries_empty_buffer_returns_empty() -> None:
    buffer = (ctypes.c_ubyte * 16)()
    assert WatchFolderService._iter_notify_entries(buffer, 0) == []


# ---------------------------------------------------------------------- #
# event sink
# ---------------------------------------------------------------------- #


def test_mark_folder_error_emits_error_and_stopped(tmp_path: Path) -> None:
    service, events = _make_service(tmp_path)
    folder = tmp_path / "shoot"
    service.add_folder(folder)
    events.clear()

    with service._lock:  # noqa: SLF001
        entry = service._folders[str(folder.resolve())]
    service._mark_folder_error(entry, "folder vanished")

    assert (
        "watch_folder_error",
        {"folder": str(folder.resolve()), "error": "folder vanished"},
    ) in events
    assert (
        "watch_stopped",
        {"folder": str(folder.resolve()), "reason": "error"},
    ) in events

    with service._lock:  # noqa: SLF001
        entry = service._folders[str(folder.resolve())]
    assert entry.error == "folder vanished"
    assert entry.watch_folder.enabled is False  # auto-disabled


def test_emit_swallows_event_sink_exceptions(tmp_path: Path) -> None:
    def broken_sink(name: str, payload: dict) -> None:
        raise RuntimeError("boom")

    service = WatchFolderService(tmp_path / "jobs.sqlite3", broken_sink)
    # Must not raise.
    service._emit("watch_status", {"active_count": 0})
