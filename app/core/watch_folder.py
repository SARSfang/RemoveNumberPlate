"""Watch folder service: detect new/modified images via ReadDirectoryChangesW.

Watcher threads (one per enabled folder) push raw file-change events into a
queue. A single aggregator thread consumes the queue, performs stability
checks (mtime-based), dedups against JobStore, and invokes the registered
enqueue callback for paths that should be processed.

Network drives are rejected at add_folder time and re-checked at start.
"""

from __future__ import annotations

import contextlib
import ctypes
import logging
import queue
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.image_io import SUPPORTED_SUFFIXES, discover_images
from app.core.job_store import JobStore
from app.domain.job import JobStatus
from app.settings import WatchFolder

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from app.desktop import EventSink

LOGGER = logging.getLogger("remove_number_plate.watch_folder")

STABILITY_THRESHOLD_SECONDS = 1.5
AGGREGATOR_POLL_INTERVAL_SECONDS = 0.5
WATCH_STATUS_INTERVAL_SECONDS = 5.0
WATCHER_JOIN_TIMEOUT_SECONDS = 1.0
AGGREGATOR_JOIN_TIMEOUT_SECONDS = 2.0
STOP_HANDLE_POLL_SECONDS = 0.01
STOP_HANDLE_POLL_ATTEMPTS = 50  # 500ms total

# Win32 constants for ReadDirectoryChangesW.
_FILE_LIST_DIRECTORY = 0x00000001
_FILE_SHARE_READ = 0x00000001
_FILE_SHARE_WRITE = 0x00000002
_OPEN_EXISTING = 3
_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
_FILE_NOTIFY_CHANGE_FILE_NAME = 0x00000001
_FILE_NOTIFY_CHANGE_DIR_NAME = 0x00000002
_FILE_NOTIFY_CHANGE_LAST_WRITE = 0x00000010
_FILE_NOTIFY_CHANGE_SIZE = 0x00000008
_FILE_ACTION_ADDED = 1
_FILE_ACTION_MODIFIED = 2
_FILE_ACTION_RENAMED_NEW_NAME = 4
_DRIVE_REMOTE = 4
_NOTIFY_BUFFER_SIZE = 4096

# Statuses that mean "already queued or in-flight" — skip re-enqueue.
_INFLIGHT_STATUSES = frozenset(
    {
        JobStatus.QUEUED,
        JobStatus.DETECTING,
        JobStatus.INPAINTING,
        JobStatus.WRITING,
    }
)

# ctypes.windll is only present on Windows. Resolve the kernel32 handle once
# at import time; non-Windows platforms get None and watcher operations raise
# at call time. Configure argtypes/restype once at module load so hot paths
# don't repeat the work and tests can swap _KERNEL32 for a fake object that
# doesn't need to support those attributes.
_KERNEL32: ctypes.WinDLL | None = None
try:  # pragma: no cover - environment dependent
    _KERNEL32 = ctypes.windll.kernel32
    _KERNEL32.CreateFileW.restype = wintypes.HANDLE
    _KERNEL32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    _KERNEL32.ReadDirectoryChangesW.restype = wintypes.BOOL
    _KERNEL32.ReadDirectoryChangesW.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    _KERNEL32.GetDriveTypeW.restype = wintypes.UINT
    _KERNEL32.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
    _KERNEL32.CloseHandle.restype = wintypes.BOOL
    _KERNEL32.CloseHandle.argtypes = [wintypes.HANDLE]
except AttributeError:  # pragma: no cover - non-Windows
    pass


class WatchFolderError(RuntimeError):
    """Raised when a watch folder cannot be added or started."""


@dataclass(frozen=True, slots=True)
class _WatchEvent:
    """Event pushed from a watcher thread to the aggregator."""

    folder: str
    file_path: str
    action: int


@dataclass(slots=True)
class WatchFolderEntry:
    """Internal mutable state for a registered watch folder."""

    watch_folder: WatchFolder
    watcher_thread: threading.Thread | None = None
    stop_event: threading.Event = field(default_factory=threading.Event)
    handle: int = 0  # win32 HANDLE; 0 = not open
    error: str | None = None


class WatchFolderService:
    """Background monitoring of folders for new/modified images."""

    def __init__(self, job_database: Path, event_sink: EventSink) -> None:
        self._job_database = job_database
        self._event_sink = event_sink
        self._folders: dict[str, WatchFolderEntry] = {}
        self._lock = threading.Lock()
        self._event_queue: queue.Queue[_WatchEvent | None] = queue.Queue()
        self._aggregator_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._enqueue_callback: Callable[[Sequence[Path]], object] | None = None
        self._captured_count = 0
        self._processed_count = 0
        self._last_status_emit = 0.0

    # ------------------------------------------------------------------ #
    # lifecycle
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        """Start the aggregator and one watcher per enabled folder."""
        if self._aggregator_thread is not None:
            return
        if _KERNEL32 is None:
            raise WatchFolderError("watch folder service requires Windows")
        self._stop_event.clear()
        self._aggregator_thread = threading.Thread(
            target=self._aggregator_loop,
            name="plate-removal-watch-aggregator",
            daemon=True,
        )
        self._aggregator_thread.start()
        with self._lock:
            entries = list(self._folders.values())
        for entry in entries:
            if entry.watch_folder.enabled and entry.error is None:
                self._start_watcher(entry)

    def stop(self) -> None:
        """Stop all watchers and the aggregator. Safe to call multiple times."""
        self._stop_event.set()
        # Wake the aggregator if it's blocked on queue.get().
        self._event_queue.put(None)
        with self._lock:
            entries = list(self._folders.values())
        for entry in entries:
            self._stop_watcher(entry)
        aggregator = self._aggregator_thread
        if aggregator is not None and aggregator is not threading.current_thread():
            aggregator.join(timeout=AGGREGATOR_JOIN_TIMEOUT_SECONDS)
        self._aggregator_thread = None

    def set_enqueue_callback(
        self,
        callback: Callable[[Sequence[Path]], object],
    ) -> None:
        """Inject the BatchService.enqueue_from_watch callback."""
        self._enqueue_callback = callback

    # ------------------------------------------------------------------ #
    # folder management (settings page calls these)
    # ------------------------------------------------------------------ #

    def add_folder(self, path: Path) -> WatchFolder:
        """Register a new watch folder. Idempotent for the same path.

        Raises WatchFolderError if the path is on a network drive.
        """
        resolved = self._resolve(path)
        if self._is_network_path(resolved):
            raise WatchFolderError("unsupported network drive")
        key = str(resolved)
        with self._lock:
            existing = self._folders.get(key)
            if existing is not None:
                return existing.watch_folder
            watch_folder = WatchFolder(
                path=key,
                enabled=True,
                added_at=datetime.now(UTC).isoformat(),
            )
            self._folders[key] = WatchFolderEntry(watch_folder=watch_folder)
        self._emit("watch_started", {"folder": key})
        # If service is already running, start the watcher immediately.
        if self._aggregator_thread is not None and not self._stop_event.is_set():
            with self._lock:
                entry = self._folders.get(key)
            if entry is not None:
                self._start_watcher(entry)
        return watch_folder

    def remove_folder(self, path: Path) -> None:
        resolved = self._resolve(path)
        key = str(resolved)
        with self._lock:
            entry = self._folders.pop(key, None)
        if entry is None:
            return
        self._stop_watcher(entry)
        self._emit("watch_stopped", {"folder": key, "reason": "removed"})

    def set_enabled(self, path: Path, enabled: bool) -> None:
        """Toggle a folder's enabled flag. Starts/stops the watcher as needed."""
        resolved = self._resolve(path)
        key = str(resolved)
        with self._lock:
            entry = self._folders.get(key)
            if entry is None:
                return
            entry.watch_folder = replace(entry.watch_folder, enabled=enabled)
            entry.error = None  # clear prior error on manual toggle
        if enabled:
            if (
                self._aggregator_thread is not None
                and not self._stop_event.is_set()
            ):
                with self._lock:
                    entry = self._folders.get(key)
                if (
                    entry is not None
                    and entry.watch_folder.enabled
                    and (entry.watcher_thread is None or not entry.watcher_thread.is_alive())
                ):
                    self._start_watcher(entry)
        else:
            with self._lock:
                entry = self._folders.get(key)
            if entry is not None:
                self._stop_watcher(entry)

    def list_folders(self) -> list[WatchFolder]:
        with self._lock:
            return [entry.watch_folder for entry in self._folders.values()]

    def list_folder_states(self) -> list[dict[str, object]]:
        """Return folder info including runtime error state (for settings UI)."""
        with self._lock:
            return [
                {
                    "path": entry.watch_folder.path,
                    "enabled": entry.watch_folder.enabled,
                    "added_at": entry.watch_folder.added_at,
                    "error": entry.error,
                }
                for entry in self._folders.values()
            ]

    def load_from_settings(self, folders: Sequence[WatchFolder]) -> None:
        """Register folders from persisted settings without starting watchers.

        Preserves the original ``enabled`` and ``added_at`` values. Folders on
        network drives are registered but marked with an error so ``start()``
        and ``rescan_existing`` skip them. Safe to call before ``start()``.
        """
        for folder in folders:
            resolved = self._resolve(Path(folder.path))
            key = str(resolved)
            with self._lock:
                if key in self._folders:
                    continue
                entry = WatchFolderEntry(watch_folder=folder)
                if self._is_network_path(resolved):
                    entry.error = "unsupported network drive"
                self._folders[key] = entry

    # ------------------------------------------------------------------ #
    # startup scan (cancellable)
    # ------------------------------------------------------------------ #

    def rescan_existing(self, cancel_event: threading.Event) -> list[Path]:
        """Walk enabled non-network folders; return paths that should enqueue.

        Returns the paths collected so far when ``cancel_event`` is set.
        """
        collected: list[Path] = []
        with self._lock:
            entries = [
                entry
                for entry in self._folders.values()
                if entry.watch_folder.enabled and entry.error is None
            ]
        try:
            with JobStore(self._job_database) as store:
                for entry in entries:
                    if cancel_event.is_set():
                        break
                    folder_path = Path(entry.watch_folder.path)
                    if self._is_network_path(folder_path):
                        continue
                    try:
                        candidates = discover_images([folder_path])
                    except OSError as error:
                        LOGGER.warning(
                            "watch folder rescan skipped %s: %s",
                            folder_path,
                            error,
                        )
                        continue
                    for candidate in candidates:
                        if cancel_event.is_set():
                            break
                        if self._should_enqueue(store, candidate):
                            collected.append(candidate)
        except Exception:
            LOGGER.exception("watch folder rescan failed")
        return collected

    # ------------------------------------------------------------------ #
    # internal: aggregator
    # ------------------------------------------------------------------ #

    def _aggregator_loop(self) -> None:
        try:
            with JobStore(self._job_database) as store:
                pending: dict[str, float] = {}
                while not self._stop_event.is_set():
                    try:
                        event = self._event_queue.get(
                            timeout=AGGREGATOR_POLL_INTERVAL_SECONDS,
                        )
                    except queue.Empty:
                        event = None
                    if event is not None:
                        pending[event.file_path] = time.time()
                    self._drain_stable(store, pending)
                    now = time.time()
                    if now - self._last_status_emit >= WATCH_STATUS_INTERVAL_SECONDS:
                        self._emit_watch_status()
        except Exception:
            LOGGER.exception("watch folder aggregator crashed")
        finally:
            LOGGER.info("watch folder aggregator exiting")

    def _drain_stable(self, store: JobStore, pending: dict[str, float]) -> None:
        """Move stable files out of pending, dedup, and enqueue survivors."""
        if not pending:
            return
        now = time.time()
        stable: list[str] = []
        for path_str in list(pending.keys()):
            path = Path(path_str)
            try:
                stat = path.stat()
            except OSError:
                # File disappeared while pending.
                pending.pop(path_str, None)
                continue
            if now - stat.st_mtime >= STABILITY_THRESHOLD_SECONDS:
                stable.append(path_str)
                pending.pop(path_str, None)
        if not stable:
            return
        to_enqueue: list[Path] = []
        for path_str in stable:
            path = Path(path_str)
            if self._should_enqueue(store, path):
                to_enqueue.append(path)
        if to_enqueue:
            self._invoke_enqueue(to_enqueue)
            self._captured_count += len(to_enqueue)
            self._emit_watch_status()

    def _invoke_enqueue(self, paths: list[Path]) -> None:
        callback = self._enqueue_callback
        if callback is None or not paths:
            return
        try:
            callback(paths)
        except Exception:
            LOGGER.exception("watch folder enqueue callback failed")

    def _emit_watch_status(self) -> None:
        self._last_status_emit = time.time()
        with self._lock:
            active_count = sum(
                1
                for entry in self._folders.values()
                if entry.watch_folder.enabled
                and entry.watcher_thread is not None
                and entry.watcher_thread.is_alive()
            )
        self._emit(
            "watch_status",
            {
                "active_count": active_count,
                "captured": self._captured_count,
                "processed": self._processed_count,
            },
        )

    # ------------------------------------------------------------------ #
    # internal: dedup (spec section 4.4)
    # ------------------------------------------------------------------ #

    def _should_enqueue(self, store: JobStore, path: Path) -> bool:
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            return False
        try:
            existing = store.get_latest_by_source(str(path.resolve()))
        except Exception:
            LOGGER.exception("dedup query failed for %s", path)
            return False
        if existing is None:
            return True  # never processed
        if existing.status is JobStatus.COMPLETED:
            # Legacy completed jobs (no mtime/size) → skip to avoid reprocessing.
            if existing.file_mtime is None or existing.file_size is None:
                return False
            try:
                stat = path.stat()
            except OSError:
                return False  # file gone
            # changed (mtime/size differ) → reprocess; unchanged → skip
            return not (
                existing.file_mtime == stat.st_mtime
                and existing.file_size == stat.st_size
            )
        # FAILED / CANCELLED / REVIEW_REQUIRED / NO_PLATE / AUTO_READY → retry.
        return existing.status not in _INFLIGHT_STATUSES

    # ------------------------------------------------------------------ #
    # internal: watcher thread
    # ------------------------------------------------------------------ #

    def _start_watcher(self, entry: WatchFolderEntry) -> None:
        if _KERNEL32 is None:
            return  # non-Windows: silently skip (tests should mock this path)
        if (
            entry.watcher_thread is not None
            and entry.watcher_thread.is_alive()
        ):
            return
        entry.stop_event.clear()
        thread = threading.Thread(
            target=self._watcher_loop,
            args=(entry,),
            name="plate-removal-watch-folder",
            daemon=True,
        )
        entry.watcher_thread = thread
        thread.start()

    def _stop_watcher(self, entry: WatchFolderEntry) -> None:
        entry.stop_event.set()
        thread = entry.watcher_thread
        if thread is not None:
            # Wait briefly for the watcher to publish its handle so we can
            # close it from here to interrupt the blocking ReadDirectoryChangesW.
            for _ in range(STOP_HANDLE_POLL_ATTEMPTS):
                if entry.handle or not thread.is_alive():
                    break
                time.sleep(STOP_HANDLE_POLL_SECONDS)
            handle = entry.handle
            if handle and _KERNEL32 is not None:
                with contextlib.suppress(OSError):
                    _KERNEL32.CloseHandle(handle)
            if thread is not threading.current_thread():
                thread.join(timeout=WATCHER_JOIN_TIMEOUT_SECONDS)
        entry.watcher_thread = None
        entry.handle = 0

    def _watcher_loop(self, entry: WatchFolderEntry) -> None:
        folder_path = entry.watch_folder.path
        try:
            handle = self._open_folder_handle(folder_path)
        except OSError as error:
            LOGGER.warning("watcher cannot open %s: %s", folder_path, error)
            self._mark_folder_error(entry, str(error))
            return
        except Exception:
            LOGGER.exception("watcher open crashed for %s", folder_path)
            self._mark_folder_error(entry, "internal error")
            return
        entry.handle = handle
        try:
            self._read_changes_loop(entry, handle)
        except OSError as error:
            if not entry.stop_event.is_set():
                LOGGER.warning("watcher %s failed: %s", folder_path, error)
                self._mark_folder_error(entry, str(error))
        except Exception:
            LOGGER.exception("watcher %s crashed", folder_path)
            if not entry.stop_event.is_set():
                self._mark_folder_error(entry, "internal error")
        finally:
            if entry.handle and _KERNEL32 is not None:
                with contextlib.suppress(OSError):
                    _KERNEL32.CloseHandle(entry.handle)
                entry.handle = 0

    def _open_folder_handle(self, folder_path: str) -> int:
        assert _KERNEL32 is not None  # noqa: S101 - guarded by caller
        handle = _KERNEL32.CreateFileW(
            folder_path,
            _FILE_LIST_DIRECTORY,
            _FILE_SHARE_READ | _FILE_SHARE_WRITE,
            None,
            _OPEN_EXISTING,
            _FILE_FLAG_BACKUP_SEMANTICS,
            None,
        )
        # CreateFileW with restype=HANDLE returns None for INVALID_HANDLE_VALUE.
        if not handle:
            raise ctypes.WinError()
        return int(handle)

    def _read_changes_loop(self, entry: WatchFolderEntry, handle: int) -> None:
        assert _KERNEL32 is not None  # noqa: S101 - guarded by caller
        buffer = (ctypes.c_ubyte * _NOTIFY_BUFFER_SIZE)()
        bytes_returned = wintypes.DWORD(0)
        notify_filter = (
            _FILE_NOTIFY_CHANGE_FILE_NAME
            | _FILE_NOTIFY_CHANGE_DIR_NAME
            | _FILE_NOTIFY_CHANGE_LAST_WRITE
            | _FILE_NOTIFY_CHANGE_SIZE
        )
        folder_path = entry.watch_folder.path
        while not entry.stop_event.is_set():
            ok = _KERNEL32.ReadDirectoryChangesW(
                handle,
                buffer,
                _NOTIFY_BUFFER_SIZE,
                True,
                notify_filter,
                ctypes.byref(bytes_returned),
                None,
                None,
            )
            if not ok:
                raise ctypes.WinError()
            if bytes_returned.value == 0:
                # Buffer overflow — some changes were lost. Continue.
                continue
            for file_name, action in self._iter_notify_entries(
                buffer,
                bytes_returned.value,
            ):
                if action in (
                    _FILE_ACTION_ADDED,
                    _FILE_ACTION_MODIFIED,
                    _FILE_ACTION_RENAMED_NEW_NAME,
                ):
                    full_path = str(Path(folder_path) / file_name)
                    self._event_queue.put(
                        _WatchEvent(
                            folder=folder_path,
                            file_path=full_path,
                            action=action,
                        ),
                    )

    @staticmethod
    def _iter_notify_entries(
        buffer: ctypes.Array[ctypes.c_ubyte],
        length: int,
    ) -> list[tuple[str, int]]:
        """Parse FILE_NOTIFY_INFORMATION records from a Win32 notify buffer."""
        entries: list[tuple[str, int]] = []
        offset = 0
        while offset + 12 <= length:
            next_offset = int.from_bytes(
                bytes(buffer[offset : offset + 4]),
                "little",
            )
            action = int.from_bytes(
                bytes(buffer[offset + 4 : offset + 8]),
                "little",
            )
            name_length = int.from_bytes(
                bytes(buffer[offset + 8 : offset + 12]),
                "little",
            )
            name_start = offset + 12
            name_end = name_start + name_length
            if name_end > length:
                break
            name_bytes = bytes(buffer[name_start:name_end])
            try:
                name = name_bytes.decode("utf-16-le")
            except UnicodeDecodeError:
                name = ""
            if name:
                entries.append((name, action))
            if next_offset == 0:
                break
            offset += next_offset
        return entries

    def _mark_folder_error(self, entry: WatchFolderEntry, error: str) -> None:
        with self._lock:
            entry.error = error
            if entry.watch_folder.enabled:
                entry.watch_folder = replace(entry.watch_folder, enabled=False)
            folder_path = entry.watch_folder.path
        self._emit(
            "watch_folder_error",
            {"folder": folder_path, "error": error},
        )
        self._emit(
            "watch_stopped",
            {"folder": folder_path, "reason": "error"},
        )

    # ------------------------------------------------------------------ #
    # internal: helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _resolve(path: Path) -> Path:
        return Path(path).resolve()

    @staticmethod
    def _is_network_path(path: Path) -> bool:
        path_str = str(path)
        if path_str.startswith("\\\\"):
            return True
        if len(path_str) >= 2 and path_str[1] == ":":
            drive = path_str[:3]
            if _KERNEL32 is None:
                return False
            try:
                return bool(_KERNEL32.GetDriveTypeW(drive) == _DRIVE_REMOTE)
            except OSError:
                return False
        return False

    def _emit(self, name: str, payload: dict[str, object]) -> None:
        try:
            self._event_sink(name, payload)
        except Exception:
            LOGGER.exception("event sink failed for %s", name)
