"""Lightweight WebView2 desktop shell and background batch service."""

from __future__ import annotations

import json
import logging
import os
import platform
import sys
import threading
import time
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import webview

from app.cli import build_manual_processor, build_processor
from app.config import PRESETS, AppPaths
from app.core.adjustment_commands import resolve_adjustment_commands
from app.core.adjustment_session import AdjustmentSessionManager
from app.core.batch import Processor
from app.core.history_search import HistoryQuery, HistorySearchService
from app.core.image_io import (
    allocate_output_path,
    copy_verified_image_atomic,
    discover_images,
    load_image,
)
from app.core.job_preview import (
    MAIN_PREVIEW_BOUNDS,
    MAIN_PREVIEW_QUALITY,
    THUMBNAIL_BOUNDS,
    THUMBNAIL_QUALITY,
    JobPreview,
    PreviewKind,
    PreviewUnavailableReason,
    build_job_preview,
    encode_preview,
)
from app.core.job_store import SCHEMA_VERSION, JobStore, StoredJob, prepare_job_database
from app.core.manual_mask import build_manual_mask
from app.core.mask_builder import MAXIMUM_MARGIN_RATIO, MINIMUM_MARGIN_RATIO
from app.core.pipeline import ManualMaskProcessor
from app.core.post_processor import PostProcessor
from app.core.project_store import (
    OutputDirectoryRule,
    ProjectPreset,
    ProjectStore,
)
from app.core.watch_folder import WatchFolderError, WatchFolderService
from app.domain.job import JobStatus
from app.domain.result import ProcessingResult
from app.infrastructure.device_probe import probe_device
from app.infrastructure.webview2 import detect_webview2_version
from app.release_readiness import inspect_models, inspect_storage
from app.settings import (
    SettingsStore,
    UserSettings,
    _parse_post_process_config,
    _post_process_config_to_dict,
)
from app.version import __display_version__, __version__

EventSink = Callable[[str, dict[str, object]], None]
ProcessorFactory = Callable[[], Processor]
ManualProcessorFactory = Callable[[], ManualMaskProcessor]
LOGGER = logging.getLogger("remove_number_plate.desktop")
SUPPORT_DOCUMENTS = {
    "user-guide": "user-guide.md",
    "troubleshooting": "troubleshooting.md",
    "privacy": "privacy.md",
}
ADJUSTABLE_STATUSES = frozenset(
    {
        JobStatus.COMPLETED,
        JobStatus.NO_PLATE,
        JobStatus.REVIEW_REQUIRED,
        JobStatus.FAILED,
        JobStatus.CANCELLED,
    }
)


def frontend_directory() -> Path:
    """Resolve bundled static assets in development and PyInstaller builds."""

    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return bundle_root / "app" / "web"


def _output_directory_rule_to_dict(rule: OutputDirectoryRule) -> dict[str, object]:
    return {
        "mode": rule.mode,
        "subfolder_name": rule.subfolder_name,
        "fixed_directory": rule.fixed_directory,
    }


def _project_to_dict(project: ProjectPreset) -> dict[str, object]:
    """Serialize a ProjectPreset for the frontend (spec v0.3.0 §3)."""

    return {
        "id": project.id,
        "name": project.name,
        "preset": project.preset,
        "mask_margin_ratio": project.mask_margin_ratio,
        "mask_margin_percent": round(project.mask_margin_ratio * 100),
        "post_process_config": _post_process_config_to_dict(
            project.post_process_config
        ),
        "output_directory_rule": _output_directory_rule_to_dict(
            project.output_directory_rule
        ),
        "created_at": project.created_at,
        "last_used_at": project.last_used_at,
    }


def _stored_job_to_dict(job: StoredJob) -> dict[str, object]:
    """Serialize a StoredJob for the frontend history listing."""

    return {
        "id": job.id,
        "name": job.source.name,
        "status": job.status.value,
        "elapsed": (
            round(job.elapsed_seconds, 3)
            if job.elapsed_seconds is not None
            else None
        ),
        "updated_at": job.updated_at,
        "error": job.error,
        "detection_count": len(job.detections),
        "risks": [risk.value for risk in job.risks],
        "source_available": job.source.is_file(),
        "output_available": bool(job.output and job.output.is_file()),
        "project_id": job.project_id,
    }


def _parse_output_directory_rule(
    raw: object,
) -> OutputDirectoryRule:
    """Parse an output directory rule from a JSON-friendly dict."""

    if raw is None:
        return OutputDirectoryRule()
    if not isinstance(raw, dict):
        raise ValueError("output_directory_rule must be an object")
    return OutputDirectoryRule(
        mode=str(raw.get("mode", "beside_source")),
        subfolder_name=str(raw.get("subfolder_name", "")),
        fixed_directory=str(raw.get("fixed_directory", "")),
    )


class BatchService:
    """Own model instances in one worker thread and publish immutable events."""

    def __init__(
        self,
        event_sink: EventSink,
        processor_factory: ProcessorFactory | None = None,
        *,
        job_database: Path | None = None,
        settings_store: SettingsStore | None = None,
    ) -> None:
        self._event_sink = event_sink
        self._processor_factory = processor_factory or (lambda: build_processor(0.60))
        self._job_database = job_database or AppPaths.default().job_database
        self._settings_store = settings_store
        self._condition = threading.Condition()
        self._busy = False
        self._paused = False
        self._cancelled = False
        self._thread: threading.Thread | None = None
        self._processor: Processor | None = None
        # Watch folder queue (spec v0.3.0 §5). Separate lock guards these
        # fields because WatchFolderService pushes from its own thread while
        # _run/_finish read on the batch thread.
        self._watch_queue: list[Path] = []
        self._watch_pending: set[str] = set()
        self._watch_lock = threading.Lock()
        # Paths belonging to the currently-running watch batch. Kept in
        # _watch_pending so duplicate enqueues are rejected while the batch
        # processes; _finish discards them once the batch ends (non-cancelled).
        self._current_batch_paths: set[str] = set()

    @property
    def busy(self) -> bool:
        with self._condition:
            return self._busy

    def replace_processor_factory(self, processor_factory: ProcessorFactory) -> bool:
        with self._condition:
            if self._busy:
                return False
            self._processor_factory = processor_factory
            self._processor = None
            return True

    def start(self, inputs: Sequence[Path]) -> bool:
        with self._condition:
            if self._busy:
                return False
            if not inputs:
                # Spec v0.3.0 §5.6: empty inputs are never accepted. Watch
                # queue continuation calls start() only with non-empty pending.
                return False
            self._busy = True
            self._paused = False
            self._cancelled = False
        self._thread = threading.Thread(
            target=self._run,
            args=(list(inputs),),
            name="plate-removal-batch",
            daemon=True,
        )
        self._emit("batch_accepted", {})
        self._thread.start()
        return True

    def pause(self) -> bool:
        with self._condition:
            if not self._busy:
                return False
            self._paused = True
        self._emit("paused", {"paused": True})
        return True

    def resume(self) -> bool:
        with self._condition:
            if not self._busy:
                return False
            self._paused = False
            self._condition.notify_all()
        self._emit("paused", {"paused": False})
        return True

    def cancel(self) -> bool:
        with self._condition:
            was_busy = self._busy
            if was_busy:
                self._cancelled = True
                self._paused = False
                self._condition.notify_all()
        # Spec v0.3.0 §5.5: cancel always clears the watch queue (explicit
        # "discard" semantics — user wants neither the current batch nor the
        # pending watch entries).
        with self._watch_lock:
            self._watch_queue.clear()
            self._watch_pending.clear()
        return was_busy

    def enqueue_from_watch(self, paths: Sequence[Path]) -> int:
        """Accept paths from WatchFolderService. Returns count actually enqueued.

        - Dedups against paths already pending (in queue or current batch).
        - If idle, drains the queue and starts a batch immediately.
        - If busy, paths wait in _watch_queue for continuation at _finish.
        """
        with self._watch_lock:
            new_paths = [
                path for path in paths if str(path) not in self._watch_pending
            ]
            if not new_paths:
                return 0
            self._watch_pending.update(str(path) for path in new_paths)
            self._watch_queue.extend(new_paths)
        self._try_drain_and_start()
        return len(new_paths)

    def _try_drain_and_start(self) -> None:
        """If idle, drain the watch queue into a new batch. Thread-safe.

        Called from enqueue_from_watch (watch thread) and _finish (batch thread
        continuation). The _condition lock makes the idle-check + batch-start
        atomic against concurrent start()/cancel().

        Paths remain in _watch_pending for the duration of the batch so that
        duplicate enqueues are rejected while processing; _finish discards
        them once the batch ends (non-cancelled only).
        """
        with self._condition:
            if self._busy:
                return
            with self._watch_lock:
                pending = list(self._watch_queue)
                self._watch_queue.clear()
                # Do NOT discard from _watch_pending here — keeping entries
                # for the duration of the batch is what makes dedup work
                # against concurrent enqueue_from_watch calls. _finish clears
                # them when the batch ends.
            if not pending:
                return
            self._busy = True
            self._paused = False
            self._cancelled = False
            self._current_batch_paths = {str(path) for path in pending}
            self._thread = threading.Thread(
                target=self._run,
                args=(pending,),
                name="plate-removal-batch",
                daemon=True,
            )
        self._emit("batch_accepted", {})
        self._thread.start()

    def wait(self, timeout: float = 10.0) -> bool:
        """Block until the service is idle (no running batch, no pending watch
        continuation). Loops across continuation batches started by _finish.
        """
        deadline = time.monotonic() + timeout
        while True:
            thread = self._thread
            if thread is not None:
                remaining = max(0.0, deadline - time.monotonic())
                thread.join(remaining)
            if not self.busy:
                return True
            if time.monotonic() >= deadline:
                return False

    def _emit(self, name: str, payload: dict[str, object]) -> None:
        self._event_sink(name, payload)

    def _maybe_post_process(
        self,
        store: JobStore,
        identifier: str,
        source: Path,
        removal_output: Path,
        sequence: int,
    ) -> None:
        """Run post-processing if enabled in settings. Failures are non-fatal.

        Reads the current settings on each call so changes to
        post_process_config take effect for the next photo. The final output
        path (which may equal ``removal_output`` when disabled or when
        post-processing falls back) is persisted to ``post_processed_output``.
        """

        if self._settings_store is None:
            return
        try:
            config = self._settings_store.load().post_process_config
        except Exception:
            LOGGER.warning(
                "post-processing skipped: settings load failed for job %s",
                identifier,
            )
            return
        if not config.enabled:
            return
        try:
            processor = PostProcessor(config)
            final_output = processor.process(
                source,
                removal_output,
                sequence=sequence,
            )
            store.set_post_processed_output(identifier, str(final_output))
            self._emit(
                "post_process_finished",
                {
                    "job_id": identifier,
                    "output": str(final_output),
                    "post_processed": final_output != removal_output,
                },
            )
        except Exception as error:
            LOGGER.warning(
                "post-processing failed for job %s: %s",
                identifier,
                error,
            )

    def _ready_for_next(self) -> bool:
        with self._condition:
            while self._paused and not self._cancelled:
                self._condition.wait()
            return not self._cancelled

    def _finish(self, cancelled: bool) -> None:
        with self._condition:
            self._busy = False
            self._paused = False
            was_cancelled = self._cancelled
            batch_paths = self._current_batch_paths
            self._current_batch_paths = set()
        # Emit cancelled=True if either the run loop signalled cancellation
        # (remaining items) or cancel() raced in mid-batch (last item done).
        self._emit("batch_finished", {"cancelled": cancelled or was_cancelled})
        # Spec v0.3.0 §5.3: continue with the next watch batch only when this
        # batch wasn't cancelled. If cancel() raced in after _finish released
        # the lock, _cancelled will be True and we skip continuation; cancel()
        # also clears _watch_queue so any racing drain finds nothing.
        if cancelled or was_cancelled:
            return
        # Release this batch's paths from dedup so future modifications can
        # re-enqueue them. (cancel() already cleared _watch_pending entirely.)
        if batch_paths:
            with self._watch_lock:
                for path_str in batch_paths:
                    self._watch_pending.discard(path_str)
        self._try_drain_and_start()

    def _run(self, inputs: list[Path]) -> None:
        try:
            sources = discover_images(inputs)
            self._emit("batch_discovered", {"total": len(sources)})
            if not sources:
                self._emit(
                    "fatal_error",
                    {"message": "没有找到支持的 JPEG、PNG 或 TIFF 图片。"},
                )
                self._finish(False)
                return
            storage = inspect_storage(sources)
            if not storage.ready:
                self._emit(
                    "fatal_error",
                    {"message": storage.issue or "输出磁盘空间预检失败。"},
                )
                self._finish(False)
                return
            with JobStore(self._job_database) as store:
                jobs = [(store.create_job(source), source) for source in sources]
                self._emit(
                    "batch_items_ready",
                    {
                        "items": [
                            {
                                "job_id": identifier,
                                "name": source.name,
                                "index": index,
                                "status": JobStatus.QUEUED.value,
                            }
                            for index, (identifier, source) in enumerate(jobs, start=1)
                        ]
                    },
                )
                processor = self._processor
                if processor is None:
                    try:
                        processor = self._processor_factory()
                    except Exception as error:
                        LOGGER.exception("AI processor initialization failed")
                        message = "AI 引擎加载失败，请重启应用后重试。"
                        for index, (identifier, source) in enumerate(jobs, start=1):
                            result = ProcessingResult(
                                None,
                                0.0,
                                status=JobStatus.FAILED,
                                error=f"{type(error).__name__}: {error}",
                            )
                            store.record_result(identifier, result)
                            self._emit(
                                "item_finished",
                                {
                                    "job_id": identifier,
                                    "name": source.name,
                                    "index": index,
                                    "total": len(jobs),
                                    "status": result.status.value,
                                    "elapsed": 0.0,
                                    "output_available": False,
                                    "detection_count": 0,
                                    "risks": [],
                                    "error": message,
                                },
                            )
                        self._emit("fatal_error", {"message": message})
                        self._finish(False)
                        return
                    self._processor = processor
                for offset, (identifier, source) in enumerate(jobs):
                    if not self._ready_for_next():
                        for pending_identifier, _pending_source in jobs[offset:]:
                            store.set_status(pending_identifier, JobStatus.CANCELLED)
                        self._finish(True)
                        return
                    index = offset + 1
                    self._emit(
                        "item_started",
                        {
                            "job_id": identifier,
                            "name": source.name,
                            "index": index,
                            "total": len(jobs),
                        },
                    )
                    started = time.perf_counter()
                    try:
                        store.set_status(identifier, JobStatus.DETECTING)
                        result = processor.process(source)
                    except Exception as error:
                        LOGGER.exception(
                            "Image processing failed for job %s (%s)",
                            identifier,
                            source.name,
                        )
                        result = ProcessingResult(
                            None,
                            time.perf_counter() - started,
                            status=JobStatus.FAILED,
                            error=f"{type(error).__name__}: {error}",
                        )
                    store.record_result(identifier, result)
                    if result.output is not None and result.status is JobStatus.COMPLETED:
                        self._maybe_post_process(
                            store,
                            identifier,
                            source,
                            result.output,
                            sequence=index,
                        )
                    self._emit(
                        "item_finished",
                        {
                            "job_id": identifier,
                            "name": source.name,
                            "index": index,
                            "total": len(jobs),
                            "status": result.status.value,
                            "elapsed": round(result.elapsed_seconds, 3),
                            "output_available": bool(result.output),
                            "detection_count": result.detection_count,
                            "risks": [risk.value for risk in result.risks],
                            "error": result.error,
                        },
                    )
        except Exception as error:
            LOGGER.exception("Batch worker failed")
            self._emit(
                "fatal_error",
                {"message": f"{type(error).__name__}: {error}"},
            )
            self._finish(False)
            return
        self._finish(False)


class DesktopApi:
    """Small allow-listed API exposed to the bundled local frontend."""

    def __init__(
        self,
        processor_factory: ProcessorFactory | None = None,
        manual_processor_factory: ManualProcessorFactory | None = None,
        *,
        job_database: Path | None = None,
    ) -> None:
        self._window: webview.Window | None = None
        self._paths = AppPaths.default()
        self._job_database = job_database or AppPaths.default().job_database
        database_backup = prepare_job_database(self._job_database)
        self._database_recovered = database_backup is not None
        if database_backup is not None:
            LOGGER.warning(
                "Recovered corrupt history database; backup=%s",
                database_backup.name,
            )
        self._settings_store = SettingsStore(self._paths.data_dir / "settings.json")
        self._settings, settings_backup = self._settings_store.load_with_recovery()
        self._settings_recovered = settings_backup is not None
        if settings_backup is not None:
            LOGGER.warning(
                "Recovered invalid settings file; backup=%s",
                settings_backup,
            )
        default_factory = processor_factory or self._processor_factory_for(
            self._settings.preset,
            self._settings.mask_margin_ratio,
        )
        self._service = BatchService(
            self._send_event,
            default_factory,
            job_database=self._job_database,
            settings_store=self._settings_store,
        )
        self._manual_processor_factory = manual_processor_factory or build_manual_processor
        self._manual_processor: ManualMaskProcessor | None = None
        self._review_lock = threading.Lock()
        self._review_busy = False
        self._adjustment_phase: str | None = None
        self._adjustments = AdjustmentSessionManager(
            self._job_database.parent / "adjustment-cache"
        )
        # Watch folder service (spec v0.3.0 §9). Initialized here but not
        # started until bootstrap() — that way DesktopApi construction in unit
        # tests doesn't spawn background threads.
        self._watch_service = WatchFolderService(
            job_database=self._job_database,
            event_sink=self._send_event,
        )
        self._watch_service.set_enqueue_callback(self._service.enqueue_from_watch)
        self._watch_service.load_from_settings(self._settings.watch_folders)
        self._watch_started = False
        self._scan_cancel = threading.Event()
        self._scan_thread: threading.Thread | None = None

    @staticmethod
    def _processor_factory_for(
        preset: str,
        mask_margin_ratio: float,
    ) -> ProcessorFactory:
        confidence = PRESETS[preset].auto_confidence
        return lambda: build_processor(confidence, mask_margin_ratio)

    def _bind_window(self, window: webview.Window) -> None:
        self._window = window

    def _send_event(self, name: str, payload: dict[str, object]) -> None:
        window = self._window
        if window is None:
            return
        value = json.dumps({"name": name, "payload": payload}, ensure_ascii=False)
        window.run_js(f"window.app.receiveBackendEvent({value});")

    def bootstrap(self) -> dict[str, object]:
        paths = AppPaths.default()
        device = probe_device()
        readiness = inspect_models(paths.model_manifest, paths.models_dir)
        model_states = [
            {
                "id": state.model_id,
                "ready": state.ready,
            }
            for state in readiness.states
        ]
        with JobStore(self._job_database) as store:
            recovered = store.recover_interrupted()
            counts = store.counts()
        # Spec v0.3.0 §3: load projects list for the project selector.
        with ProjectStore(self._job_database) as store:
            projects = store.list_projects()
        # Spec v0.3.0 §9: start watch service and async scan before the
        # frontend begins interacting. Idempotent — safe if bootstrap() is
        # called more than once.
        self._start_watch_service()
        return {
            "version": __display_version__,
            "version_raw": __version__,
            "gpu": device.gpu_name or "未检测到独立显卡",
            "cuda_available": False,
            "models_ready": readiness.ready,
            "model_states": model_states,
            "model_issue": readiness.issue,
            "history_counts": counts,
            "recovered_jobs": recovered,
            "database_recovered": self._database_recovered,
            "settings_recovered": self._settings_recovered,
            "runtime": "轻量 ONNX Runtime · 本地离线处理",
            "schema_version": SCHEMA_VERSION,
            "webview2_version": detect_webview2_version() or "未检测到",
            "preset": self._settings.preset,
            "mask_margin_percent": round(self._settings.mask_margin_ratio * 100),
            "watch_folders": self._watch_service.list_folder_states(),
            "watch_scan_in_progress": self._scan_thread is not None
            and self._scan_thread.is_alive(),
            "post_process_config": _post_process_config_to_dict(
                self._settings.post_process_config
            ),
            "projects": [_project_to_dict(project) for project in projects],
            "current_project_id": self._settings.current_project_id,
        }

    def _start_watch_service(self) -> None:
        """Start the watch service and an asynchronous startup scan.

        Idempotent: calling it again after the service is already running is a
        no-op. The scan runs on a daemon thread and can be cancelled via
        ``cancel_watch_scan``.
        """
        if self._watch_started:
            return
        try:
            self._watch_service.start()
        except WatchFolderError as error:
            LOGGER.warning("watch service failed to start: %s", error)
            return
        self._watch_started = True
        self._scan_cancel.clear()
        self._scan_thread = threading.Thread(
            target=self._run_startup_scan,
            name="watch-folder-startup-scan",
            daemon=True,
        )
        self._scan_thread.start()

    def _run_startup_scan(self) -> None:
        self._send_event("watch_scan_started", {})
        collected: list[Path] = []
        try:
            collected = self._watch_service.rescan_existing(self._scan_cancel)
            if collected and not self._scan_cancel.is_set():
                self._service.enqueue_from_watch(collected)
        except Exception:
            LOGGER.exception("watch folder startup scan crashed")
        finally:
            self._send_event(
                "watch_scan_complete",
                {
                    "collected_count": len(collected),
                    "cancelled": self._scan_cancel.is_set(),
                },
            )

    def set_preset(self, preset: str) -> dict[str, object]:
        if preset not in PRESETS:
            return {"accepted": False, "message": "未知的处理预设。"}
        if not self._service.replace_processor_factory(
            self._processor_factory_for(preset, self._settings.mask_margin_ratio)
        ):
            return {
                "accepted": False,
                "message": "当前批次运行中，请在处理结束后更改预设。",
            }
        self._settings = UserSettings(
            preset=preset,
            mask_margin_ratio=self._settings.mask_margin_ratio,
        )
        self._settings_store.save(self._settings)
        return {"accepted": True, "message": "处理预设已保存。"}

    def set_mask_margin(self, percent: int | float) -> dict[str, object]:
        """Persist the shared automatic and editor mask-margin default."""

        if isinstance(percent, bool) or not isinstance(percent, (int, float)):
            return {"accepted": False, "message": "边缘扩展值无效。"}
        ratio = float(percent) / 100
        if not MINIMUM_MARGIN_RATIO <= ratio <= MAXIMUM_MARGIN_RATIO:
            return {
                "accepted": False,
                "message": "边缘扩展必须在 -30% 到 +100% 之间。",
            }
        if not self._service.replace_processor_factory(
            self._processor_factory_for(self._settings.preset, ratio)
        ):
            return {
                "accepted": False,
                "message": "当前批次运行中，请在处理结束后修改边缘扩展。",
            }
        self._settings = UserSettings(
            preset=self._settings.preset,
            mask_margin_ratio=ratio,
        )
        self._settings_store.save(self._settings)
        return {"accepted": True, "message": "默认边缘扩展已保存。"}

    def get_post_process_config(self) -> dict[str, object]:
        """Return the current post-processing configuration."""

        settings = self._settings_store.load()
        return _post_process_config_to_dict(settings.post_process_config)

    def set_post_process_config(self, config: dict[str, object]) -> dict[str, object]:
        """Persist the post-processing configuration.

        Uses ``dataclasses.replace`` so existing preset, mask margin and watch
        folder fields are preserved verbatim.
        """

        try:
            parsed = _parse_post_process_config(config)
        except (ValueError, TypeError, AttributeError):
            return {"accepted": False, "message": "后处理配置无效。"}
        settings = self._settings_store.load()
        new_settings = replace(settings, post_process_config=parsed)
        self._settings_store.save(new_settings)
        self._settings = new_settings
        return {"accepted": True, "message": "后处理配置已保存。"}

    def preview_naming(self, template: str, sample_name: str) -> dict[str, object]:
        """Render a naming template against a sample filename for the UI."""

        from app.core.naming_template import NamingContext, NamingTemplate

        if not isinstance(template, str) or not isinstance(sample_name, str):
            return {"preview": ""}
        sample = Path(sample_name)
        parsed = NamingTemplate(template)
        context = NamingContext(
            original_stem=sample.stem,
            extension=sample.suffix,
            sequence=1,
            client="客户名",
            shot_date="20260729",
        )
        return {"preview": parsed.render(context)}

    def list_history(self, limit: int = 100) -> list[dict[str, object]]:
        safe_limit = max(1, min(int(limit), 500))
        with JobStore(self._job_database) as store:
            jobs = store.list_jobs(limit=safe_limit)
        return [_stored_job_to_dict(job) for job in jobs]

    def search_history(self, query: dict[str, Any] | None = None) -> dict[str, object]:
        """Search jobs with flexible filtering (spec v0.3.0 §4).

        ``query`` fields (all optional):
          - statuses: list[str]      Status multi-select
          - date_from: str | None    ISO date (YYYY-MM-DD), inclusive
          - date_to: str | None      ISO date (YYYY-MM-DD), inclusive
          - name_contains: str       Case-insensitive filename substring
          - project_ids: list[str]   Project multi-select
          - include_no_project: bool Include jobs with no project (default True)
          - limit: int               Page size (default 500)
          - offset: int              Page offset (default 0)
        """

        raw = query or {}
        try:
            statuses = tuple(str(s) for s in (raw.get("statuses") or ()))
            project_ids = tuple(str(p) for p in (raw.get("project_ids") or ()))
            history_query = HistoryQuery(
                statuses=statuses,
                date_from=raw.get("date_from") or None,
                date_to=raw.get("date_to") or None,
                name_contains=str(raw.get("name_contains") or ""),
                project_ids=project_ids,
                include_no_project=bool(raw.get("include_no_project", True)),
                limit=max(1, min(int(raw.get("limit", 500)), 500)),
                offset=max(0, int(raw.get("offset", 0))),
            )
        except (TypeError, ValueError):
            return {"jobs": [], "total": 0}
        service = HistorySearchService(self._job_database)
        jobs = service.search(history_query)
        total = service.count(history_query)
        return {"jobs": [_stored_job_to_dict(job) for job in jobs], "total": total}

    def queue_for_manual_review(self, identifier: str) -> dict[str, object]:
        with JobStore(self._job_database) as store:
            job = store.get_job(identifier)
            if job.status is not JobStatus.NO_PLATE:
                return {
                    "accepted": False,
                    "message": "只有“未发现车牌”的照片可转入人工复核。",
                }
            store.set_status(identifier, JobStatus.REVIEW_REQUIRED)
        self._send_event("history_changed", {})
        return {"accepted": True, "message": "已加入待复核，可手动画出车牌区域。"}

    def retry_job(self, identifier: str) -> dict[str, object]:
        with JobStore(self._job_database) as store:
            job = store.get_job(identifier)
            if job.status not in {
                JobStatus.QUEUED,
                JobStatus.FAILED,
                JobStatus.CANCELLED,
            }:
                return {"accepted": False, "message": "这个任务当前不能重新处理。"}
            if not job.source.is_file():
                return {"accepted": False, "message": "原照片已移动或删除，无法重新处理。"}
            accepted = self._service.start([job.source])
            if accepted and job.status is JobStatus.QUEUED:
                store.set_status(identifier, JobStatus.CANCELLED)
        return {
            "accepted": accepted,
            "message": "已重新加入处理队列。" if accepted else "当前已有批次正在运行。",
        }

    def export_diagnostics(self) -> dict[str, object]:
        if self._window is None:
            return {"accepted": False, "message": "桌面窗口尚未就绪。"}
        selected = self._window.create_file_dialog(
            webview.FileDialog.SAVE,
            save_filename=f"消除车牌-诊断-{int(time.time())}.zip",
            file_types=("ZIP 压缩包 (*.zip)",),
        )
        if not selected:
            return {"accepted": False, "message": ""}
        value = selected[0] if isinstance(selected, (list, tuple)) else selected
        destination = Path(str(value))
        if destination.suffix.lower() != ".zip":
            destination = destination.with_suffix(".zip")
        destination.parent.mkdir(parents=True, exist_ok=True)
        device = probe_device()
        diagnostics = {
            "app_version": __version__,
            "platform": platform.platform(),
            "python": platform.python_version(),
            "frozen": bool(getattr(sys, "frozen", False)),
            "webview2": detect_webview2_version(),
            "onnx_providers": list(device.onnx_providers),
            "preset": self._settings.preset,
            "job_counts": self._history_counts(),
            "database_recovered": self._database_recovered,
            "settings_recovered": self._settings_recovered,
        }
        with zipfile.ZipFile(
            destination,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:
            archive.writestr(
                "diagnostics.json",
                json.dumps(diagnostics, ensure_ascii=False, indent=2),
            )
            if self._paths.log_dir.exists():
                for log_path in sorted(self._paths.log_dir.glob("application.log*")):
                    archive.write(log_path, f"logs/{log_path.name}")
        return {
            "accepted": True,
            "message": "诊断包已导出；其中不包含照片、文件路径或任务数据库。",
            "path": str(destination),
        }

    def open_support_document(self, document: str) -> bool:
        filename = SUPPORT_DOCUMENTS.get(document)
        if filename is None:
            return False
        target = self._paths.project_root / "docs" / filename
        if not target.is_file():
            return False
        os.startfile(target)
        return True

    def _history_counts(self) -> dict[str, int]:
        with JobStore(self._job_database) as store:
            return store.counts()

    def frontend_ready(self) -> bool:
        """Acknowledge that assets and the JS bridge completed initialization."""

        return True

    def list_review_jobs(self) -> list[dict[str, object]]:
        with JobStore(self._job_database) as store:
            jobs = store.list_jobs((JobStatus.REVIEW_REQUIRED,))
        return [
            {
                "id": job.id,
                "name": job.source.name,
                "risks": [risk.value for risk in job.risks],
                "detection_count": len(job.detections),
            }
            for job in jobs
        ]

    def get_adjustment_job(self, identifier: str) -> dict[str, object]:
        """Load any non-processing photo into the shared adjustment editor."""

        try:
            with JobStore(self._job_database) as store:
                job = store.get_job(identifier)
                revision_entry = store.latest_mask_revision_entry(identifier)
        except KeyError:
            return {
                "id": "",
                "name": "",
                "status": "",
                "entry_available": False,
                "message": "找不到这张照片。",
            }
        if job.status not in ADJUSTABLE_STATUSES:
            return {
                "id": job.id,
                "name": job.source.name,
                "status": job.status.value,
                "entry_available": False,
                "message": "照片处理完成后即可调整区域。",
            }
        preview = build_job_preview(job, PreviewKind.ORIGINAL)
        if not preview.available:
            return {
                "id": job.id,
                "name": job.source.name,
                "status": job.status.value,
                "entry_available": False,
                "message": preview.message,
            }
        revision, commands = (
            revision_entry if revision_entry is not None else ("base", [])
        )
        return {
            "id": job.id,
            "name": job.source.name,
            "status": job.status.value,
            "entry_available": True,
            "message": "",
            "image": preview.image,
            "width": preview.width,
            "height": preview.height,
            "preview_width": preview.preview_width,
            "preview_height": preview.preview_height,
            "revision": revision,
            "detections": [
                {
                    "id": f"detection:{index}",
                    "points": [
                        [point[0], point[1]]
                        for point in detection.effective_polygon.points
                    ],
                    "confidence": detection.confidence,
                }
                for index, detection in enumerate(job.detections)
            ],
            "commands": commands,
            "default_margin_ratio": self._settings.mask_margin_ratio,
            "risks": [risk.value for risk in job.risks],
            "has_result": bool(job.output and job.output.is_file()),
        }

    def get_review_job(self, identifier: str) -> dict[str, object]:
        with JobStore(self._job_database) as store:
            job = store.get_job(identifier)
            commands = store.latest_mask_revision(identifier)
        if job.status is not JobStatus.REVIEW_REQUIRED:
            raise ValueError("job is not awaiting review")
        preview = build_job_preview(job, PreviewKind.ORIGINAL)
        if not preview.available:
            raise ValueError(preview.message)
        return {
            "id": job.id,
            "name": job.source.name,
            "image": preview.image,
            "width": preview.width,
            "height": preview.height,
            "preview_width": preview.preview_width,
            "preview_height": preview.preview_height,
            "detections": [
                {
                    "id": f"detection:{index}",
                    "x1": detection.box.x1,
                    "y1": detection.box.y1,
                    "x2": detection.box.x2,
                    "y2": detection.box.y2,
                    "confidence": detection.confidence,
                    "points": [
                        [point[0], point[1]]
                        for point in detection.effective_polygon.points
                    ],
                }
                for index, detection in enumerate(job.detections)
            ],
            "commands": commands,
            "default_margin_ratio": self._settings.mask_margin_ratio,
            "risks": [risk.value for risk in job.risks],
        }

    def preview_adjustment(
        self,
        identifier: str,
        revision: str,
        commands: list[dict[str, object]],
    ) -> dict[str, object]:
        """Validate and asynchronously render a temporary edited result."""

        try:
            with JobStore(self._job_database) as store:
                job = store.get_job(identifier)
                revision_entry = store.latest_mask_revision_entry(identifier)
            current_revision = revision_entry[0] if revision_entry is not None else "base"
            if revision != current_revision:
                return {
                    "accepted": False,
                    "message": "这张照片已在其他操作中更新，请重新打开后再调整。",
                }
            if job.status not in ADJUSTABLE_STATUSES:
                return {"accepted": False, "message": "照片处理完成后才能调整区域。"}
            if not job.source.is_file():
                return {"accepted": False, "message": "原照片已移动或删除。"}
            loaded = load_image(job.source)
            image_shape = (
                int(loaded.pixels_rgb.shape[0]),
                int(loaded.pixels_rgb.shape[1]),
            )
            resolve_adjustment_commands(image_shape, job.detections, commands)
        except (KeyError, ValueError) as error:
            return {"accepted": False, "message": str(error)}

        with self._review_lock:
            if self._review_busy or self._service.busy:
                return {"accepted": False, "message": "当前有其他 AI 任务正在运行。"}
            generation = self._adjustments.begin(identifier, revision, commands)
            self._review_busy = True
            self._adjustment_phase = "rendering"
        self._send_event("adjustment_preview_started", {"job_id": identifier})
        threading.Thread(
            target=self._run_adjustment_preview,
            args=(identifier, revision, commands, generation),
            name="plate-removal-adjustment-preview",
            daemon=True,
        ).start()
        return {"accepted": True, "message": ""}

    def _run_adjustment_preview(
        self,
        identifier: str,
        revision: str,
        commands: list[dict[str, object]],
        generation: str,
    ) -> None:
        try:
            with JobStore(self._job_database) as store:
                job = store.get_job(identifier)
                revision_entry = store.latest_mask_revision_entry(identifier)
            current_revision = revision_entry[0] if revision_entry is not None else "base"
            if current_revision != revision:
                raise ValueError("adjustment revision changed before rendering")
            loaded = load_image(job.source)
            image_shape = (
                int(loaded.pixels_rgb.shape[0]),
                int(loaded.pixels_rgb.shape[1]),
            )
            mask = build_manual_mask(image_shape, job.detections, commands)
            processor = self._manual_processor
            if processor is None:
                processor = self._manual_processor_factory()
                self._manual_processor = processor
            cache_path = self._adjustments.cache_path(generation, job.source.suffix)
            result = processor.render_to(job.source, mask, cache_path)
            session = self._adjustments.complete(
                generation,
                cache_path,
                width=image_shape[1],
                height=image_shape[0],
                elapsed_seconds=result.elapsed_seconds,
            )
            if session is None:
                return
            preview = encode_preview(
                cache_path,
                variant=PreviewKind.RESULT,
                bounds=MAIN_PREVIEW_BOUNDS,
                quality=MAIN_PREVIEW_QUALITY,
            )
            if not preview.available:
                raise ValueError(preview.message)
            self._send_event(
                "adjustment_preview_ready",
                {
                    "job_id": identifier,
                    "preview_token": session.preview_token,
                    "image": preview.image,
                    "width": preview.width,
                    "height": preview.height,
                    "preview_width": preview.preview_width,
                    "preview_height": preview.preview_height,
                    "elapsed": round(result.elapsed_seconds, 3),
                },
            )
        except Exception as error:
            LOGGER.exception("Adjustment preview failed for job %s", identifier)
            if self._adjustments.cancel(identifier):
                self._send_event(
                    "adjustment_preview_failed",
                    {
                        "job_id": identifier,
                        "message": f"{type(error).__name__}: {error}",
                    },
                )
        finally:
            with self._review_lock:
                self._review_busy = False
                self._adjustment_phase = None

    def save_adjustment(
        self,
        identifier: str,
        preview_token: str,
    ) -> dict[str, object]:
        """Commit a validated cache as a new versioned output."""

        try:
            session = self._adjustments.get(identifier, preview_token)
            with JobStore(self._job_database) as store:
                store.get_job(identifier)
                revision_entry = store.latest_mask_revision_entry(identifier)
            current_revision = revision_entry[0] if revision_entry is not None else "base"
            if current_revision != session.revision:
                return {
                    "accepted": False,
                    "message": "这张照片已更新，当前临时预览不能再保存。",
                }
        except (KeyError, ValueError) as error:
            return {"accepted": False, "message": str(error)}

        with self._review_lock:
            if self._review_busy or self._service.busy:
                return {"accepted": False, "message": "当前有其他任务正在运行。"}
            self._review_busy = True
            self._adjustment_phase = "saving"
        self._send_event("adjustment_save_started", {"job_id": identifier})
        threading.Thread(
            target=self._run_adjustment_save,
            args=(identifier, preview_token),
            name="plate-removal-adjustment-save",
            daemon=True,
        ).start()
        return {"accepted": True, "message": ""}

    def _run_adjustment_save(
        self,
        identifier: str,
        preview_token: str,
    ) -> None:
        output: Path | None = None
        committed = False
        try:
            session = self._adjustments.get(identifier, preview_token)
            with JobStore(self._job_database) as store:
                job = store.get_job(identifier)
                revision_entry = store.latest_mask_revision_entry(identifier)
                current_revision = (
                    revision_entry[0] if revision_entry is not None else "base"
                )
                if current_revision != session.revision:
                    raise ValueError("adjustment revision changed before saving")
                while True:
                    output = allocate_output_path(job.source)
                    try:
                        copy_verified_image_atomic(session.cache_path, output)
                        break
                    except FileExistsError:
                        continue
                store.record_adjustment_result(
                    identifier,
                    output,
                    session.commands,
                    elapsed_seconds=session.elapsed_seconds,
                )
                committed = True
            self._adjustments.finish(preview_token)
            self._send_event(
                "adjustment_saved",
                {
                    "job_id": identifier,
                    "status": JobStatus.COMPLETED.value,
                    "output_name": output.name,
                    "elapsed": round(session.elapsed_seconds, 3),
                },
            )
            self._send_event("history_changed", {})
        except Exception as error:
            if output is not None and output.is_file() and not committed:
                output.unlink(missing_ok=True)
            LOGGER.exception("Adjustment save failed for job %s", identifier)
            self._send_event(
                "adjustment_save_failed",
                {
                    "job_id": identifier,
                    "message": f"{type(error).__name__}: {error}",
                },
            )
        finally:
            with self._review_lock:
                self._review_busy = False
                self._adjustment_phase = None

    def cancel_adjustment(self, identifier: str) -> dict[str, object]:
        with self._review_lock:
            if self._adjustment_phase == "saving":
                return {
                    "accepted": False,
                    "message": "正在保存新结果，请稍候。",
                }
            cancelled = self._adjustments.cancel(identifier)
        return {"accepted": True, "cancelled": cancelled, "message": ""}

    def reprocess_review(
        self,
        identifier: str,
        commands: list[dict[str, object]],
    ) -> dict[str, object]:
        with self._review_lock:
            if self._review_busy or self._service.busy:
                return {"accepted": False, "message": "当前有其他 AI 任务正在运行。"}
            self._review_busy = True
        threading.Thread(
            target=self._run_review,
            args=(identifier, commands),
            name="plate-removal-review",
            daemon=True,
        ).start()
        return {"accepted": True, "message": ""}

    def _run_review(
        self,
        identifier: str,
        commands: list[dict[str, object]],
    ) -> None:
        self._send_event("review_started", {"job_id": identifier})
        try:
            with JobStore(self._job_database) as store:
                job = store.get_job(identifier)
                if job.status is not JobStatus.REVIEW_REQUIRED:
                    raise ValueError("job is not awaiting review")
                loaded = load_image(job.source)
                mask = build_manual_mask(
                    (
                        int(loaded.pixels_rgb.shape[0]),
                        int(loaded.pixels_rgb.shape[1]),
                    ),
                    job.detections,
                    commands,
                )
                processor = self._manual_processor
                if processor is None:
                    processor = self._manual_processor_factory()
                    self._manual_processor = processor
                result = processor.process(job.source, mask)
                if result.output is None:
                    raise ValueError("manual processing did not create an output")
                store.record_adjustment_result(
                    identifier,
                    result.output,
                    commands,
                    elapsed_seconds=result.elapsed_seconds,
                )
            self._send_event(
                "review_finished",
                {
                    "job_id": identifier,
                    "status": result.status.value,
                    "output": str(result.output) if result.output else None,
                    "elapsed": round(result.elapsed_seconds, 3),
                },
            )
        except Exception as error:
            LOGGER.exception("Manual review failed for job %s", identifier)
            self._send_event(
                "review_failed",
                {
                    "job_id": identifier,
                    "message": f"{type(error).__name__}: {error}",
                },
            )
        finally:
            with self._review_lock:
                self._review_busy = False

    def skip_review(self, identifier: str) -> bool:
        with self._review_lock:
            if self._review_busy:
                return False
            with JobStore(self._job_database) as store:
                job = store.get_job(identifier)
                if job.status is not JobStatus.REVIEW_REQUIRED:
                    return False
                store.set_status(identifier, JobStatus.CANCELLED)
        self._send_event("review_skipped", {"job_id": identifier})
        return True

    def choose_files(self) -> list[str]:
        if self._window is None:
            return []
        values = self._window.create_file_dialog(
            webview.FileDialog.OPEN,
            allow_multiple=True,
            file_types=("照片 (*.jpg;*.jpeg;*.png;*.tif;*.tiff)",),
        )
        return list(values or ())

    def choose_folder(self) -> list[str]:
        if self._window is None:
            return []
        values = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        return list(values or ())

    def choose_watermark_image(self) -> dict[str, object]:
        """Open a file dialog to pick a watermark image.

        Returns ``{"accepted": True, "path": "..."}`` on success, or
        ``{"accepted": False, "message": "..."}`` when cancelled or unavailable.
        """
        if self._window is None:
            return {"accepted": False, "message": "桌面窗口尚未就绪。"}
        values = self._window.create_file_dialog(
            webview.FileDialog.OPEN,
            allow_multiple=False,
            file_types=("图片 (*.png;*.jpg;*.jpeg;*.bmp;*.tif;*.tiff)",),
        )
        if not values:
            return {"accepted": False, "message": ""}
        raw = values[0] if isinstance(values, (list, tuple)) else values
        return {"accepted": True, "path": str(raw)}

    def start_batch(self, paths: list[str]) -> dict[str, object]:
        safe_paths = [Path(value) for value in paths if Path(value).exists()]
        if not safe_paths:
            return {"accepted": False, "message": "没有收到有效的文件或文件夹。"}
        readiness = inspect_models(
            self._paths.model_manifest,
            self._paths.models_dir,
        )
        if not readiness.ready:
            return {
                "accepted": False,
                "message": readiness.issue or "AI 模型未通过完整性校验，请重新安装。",
            }
        accepted = self._service.start(safe_paths)
        return {
            "accepted": accepted,
            "message": "" if accepted else "已有一个批次正在处理中。",
        }

    def pause(self) -> bool:
        return self._service.pause()

    def resume(self) -> bool:
        return self._service.resume()

    def cancel(self) -> bool:
        return self._service.cancel()

    # ------------------------------------------------------------------ #
    # watch folder management (spec v0.3.0 §7.4)
    # ------------------------------------------------------------------ #

    def list_watch_folders(self) -> list[dict[str, object]]:
        """Return registered watch folders with runtime error state."""
        return self._watch_service.list_folder_states()

    def add_watch_folder(self) -> dict[str, object]:
        """Open the system folder picker and register the chosen folder.

        Returns ``{"accepted": True, "folder": {...}}`` on success, or
        ``{"accepted": False, "message": "..."}`` when the user cancels, the
        folder is on a network drive, or registration fails.
        """
        if self._window is None:
            return {"accepted": False, "message": "桌面窗口尚未就绪。"}
        values = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        if not values:
            return {"accepted": False, "message": ""}
        raw_path = values[0] if isinstance(values, (list, tuple)) else values
        path = Path(str(raw_path))
        try:
            folder = self._watch_service.add_folder(path)
        except WatchFolderError:
            return {
                "accepted": False,
                "message": "不支持网络驱动器，请选择本地磁盘上的文件夹。",
            }
        self._persist_watch_folders()
        return {
            "accepted": True,
            "message": "",
            "folder": {
                "path": folder.path,
                "enabled": folder.enabled,
                "added_at": folder.added_at,
                "error": None,
            },
        }

    def remove_watch_folder(self, path: str) -> dict[str, object]:
        """Remove a watch folder by its path string."""
        self._watch_service.remove_folder(Path(path))
        self._persist_watch_folders()
        return {"accepted": True, "message": ""}

    def set_watch_folder_enabled(
        self,
        path: str,
        enabled: bool,
    ) -> dict[str, object]:
        """Toggle a watch folder's enabled flag."""
        self._watch_service.set_enabled(Path(path), enabled)
        self._persist_watch_folders()
        return {"accepted": True, "message": ""}

    def cancel_watch_scan(self) -> dict[str, object]:
        """Cancel an in-progress startup scan. Already-collected paths enqueue."""
        self._scan_cancel.set()
        return {"accepted": True, "message": ""}

    def _persist_watch_folders(self) -> None:
        """Sync the watch service's folder list back to settings.json."""
        folders = self._watch_service.list_folders()
        self._settings = UserSettings(
            preset=self._settings.preset,
            mask_margin_ratio=self._settings.mask_margin_ratio,
            watch_folders=tuple(folders),
        )
        self._settings_store.save(self._settings)

    # ------------------------------------------------------------------ #
    # project / preset management (spec v0.3.0 §3)
    # ------------------------------------------------------------------ #

    def list_projects(self) -> dict[str, object]:
        """Return all projects ordered by last_used_at DESC, name ASC."""

        with ProjectStore(self._job_database) as store:
            projects = store.list_projects()
        return {"projects": [_project_to_dict(project) for project in projects]}

    def create_project(
        self,
        name: str,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        """Create a new project preset.

        ``payload`` may include:
          - preset: str                    Processing preset (default "balanced")
          - mask_margin_ratio: float       Edge expansion ratio (default 0.08)
          - post_process_config: dict     Post-processing config
          - output_directory_rule: dict   Output directory rule
        """

        raw = payload or {}
        if not isinstance(name, str) or not name.strip():
            return {"accepted": False, "message": "项目名称不能为空。"}
        preset = str(raw.get("preset", "balanced"))
        if preset not in PRESETS:
            return {"accepted": False, "message": "未知的处理预设。"}
        try:
            margin_value: Any = raw.get("mask_margin_ratio", 0.08)
            mask_margin_ratio = float(margin_value)
        except (TypeError, ValueError):
            return {"accepted": False, "message": "边缘扩展值无效。"}
        if not MINIMUM_MARGIN_RATIO <= mask_margin_ratio <= MAXIMUM_MARGIN_RATIO:
            return {
                "accepted": False,
                "message": f"边缘扩展必须在 {round(MINIMUM_MARGIN_RATIO * 100)}% "
                f"到 {round(MAXIMUM_MARGIN_RATIO * 100)}% 之间。",
            }
        try:
            post_process_config = _parse_post_process_config(
                raw.get("post_process_config")
            )
            output_directory_rule = _parse_output_directory_rule(
                raw.get("output_directory_rule")
            )
        except (TypeError, ValueError) as error:
            return {"accepted": False, "message": str(error)}
        try:
            with ProjectStore(self._job_database) as store:
                project = store.create_project(
                    name.strip(),
                    preset=preset,
                    mask_margin_ratio=mask_margin_ratio,
                    post_process_config=post_process_config,
                    output_directory_rule=output_directory_rule,
                )
        except ValueError as error:
            return {"accepted": False, "message": str(error)}
        self._send_event("projects_changed", {})
        return {"accepted": True, "message": "", "project": _project_to_dict(project)}

    def update_project(
        self,
        project_id: str,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        """Update an existing project. Accepts the same payload as create."""

        raw = payload or {}
        updates: dict[str, object] = {}
        if "name" in raw:
            name = str(raw["name"])
            if not name.strip():
                return {"accepted": False, "message": "项目名称不能为空。"}
            updates["name"] = name.strip()
        if "preset" in raw:
            preset = str(raw["preset"])
            if preset not in PRESETS:
                return {"accepted": False, "message": "未知的处理预设。"}
            updates["preset"] = preset
        if "mask_margin_ratio" in raw:
            try:
                margin_value: Any = raw["mask_margin_ratio"]
                ratio = float(margin_value)
            except (TypeError, ValueError):
                return {"accepted": False, "message": "边缘扩展值无效。"}
            if not MINIMUM_MARGIN_RATIO <= ratio <= MAXIMUM_MARGIN_RATIO:
                return {
                    "accepted": False,
                    "message": f"边缘扩展必须在 {round(MINIMUM_MARGIN_RATIO * 100)}% "
                    f"到 {round(MAXIMUM_MARGIN_RATIO * 100)}% 之间。",
                }
            updates["mask_margin_ratio"] = ratio
        if "post_process_config" in raw:
            try:
                updates["post_process_config"] = _parse_post_process_config(
                    raw["post_process_config"]
                )
            except (TypeError, ValueError) as error:
                return {"accepted": False, "message": str(error)}
        if "output_directory_rule" in raw:
            try:
                updates["output_directory_rule"] = _parse_output_directory_rule(
                    raw["output_directory_rule"]
                )
            except (TypeError, ValueError) as error:
                return {"accepted": False, "message": str(error)}
        try:
            with ProjectStore(self._job_database) as store:
                project = store.update_project(project_id, **updates)
        except KeyError:
            return {"accepted": False, "message": "项目不存在。"}
        except ValueError as error:
            return {"accepted": False, "message": str(error)}
        self._send_event("projects_changed", {})
        return {"accepted": True, "message": "", "project": _project_to_dict(project)}

    def delete_project(self, project_id: str) -> dict[str, object]:
        """Delete a project. Associated jobs have project_id set to NULL."""

        with ProjectStore(self._job_database) as store:
            deleted = store.delete_project(project_id)
        if not deleted:
            return {"accepted": False, "message": "项目不存在。"}
        # Spec v0.3.0 §3: if the deleted project was current, clear the
        # current_project_id so the frontend drops the selector.
        if self._settings.current_project_id == project_id:
            new_settings = replace(self._settings, current_project_id=None)
            self._settings_store.save(new_settings)
            self._settings = new_settings
        self._send_event("projects_changed", {})
        return {"accepted": True, "message": ""}

    def set_current_project(
        self,
        project_id: str | None,
    ) -> dict[str, object]:
        """Switch the current project (spec v0.3.0 §3.2).

        Persists ``current_project_id`` to settings.json and touches the
        project's ``last_used_at`` for ordering. Pass ``None`` or an empty
        string to clear.
        """

        target = project_id or None
        if target is not None and not isinstance(target, str):
            return {"accepted": False, "message": "项目 ID 无效。"}
        new_settings = replace(self._settings, current_project_id=target)
        self._settings_store.save(new_settings)
        self._settings = new_settings
        if target:
            try:
                with ProjectStore(self._job_database) as store:
                    store.touch_last_used(target)
            except KeyError:
                return {"accepted": False, "message": "项目不存在。"}
        return {"accepted": True, "message": ""}

    # ------------------------------------------------------------------ #
    # shutdown (spec v0.3.0 §9.2)
    # ------------------------------------------------------------------ #

    def shutdown(self) -> None:
        """Stop the watch service and wait for the batch to drain.

        Called from the window-closing hook in ``launch()``.
        """
        self._scan_cancel.set()
        self._watch_service.stop()
        self._watch_started = False
        self._service.wait(timeout=5.0)

    @staticmethod
    def _preview_unavailable(
        variant: str,
        reason: PreviewUnavailableReason,
    ) -> dict[str, object]:
        return JobPreview.unavailable(variant, reason).as_dict()

    def get_job_thumbnail(self, identifier: str) -> dict[str, object]:
        try:
            with JobStore(self._job_database) as store:
                job = store.get_job(identifier)
        except KeyError:
            return self._preview_unavailable(
                "thumbnail",
                PreviewUnavailableReason.UNKNOWN_JOB,
            )
        kind = PreviewKind.RESULT if job.output is not None else PreviewKind.ORIGINAL
        preview = build_job_preview(
            job,
            kind,
            bounds=THUMBNAIL_BOUNDS,
            quality=THUMBNAIL_QUALITY,
        )
        if not preview.available and kind is PreviewKind.RESULT:
            preview = build_job_preview(
                job,
                PreviewKind.ORIGINAL,
                bounds=THUMBNAIL_BOUNDS,
                quality=THUMBNAIL_QUALITY,
            )
        return preview.as_dict()

    def get_job_preview(self, identifier: str, variant: str) -> dict[str, object]:
        try:
            kind = PreviewKind(variant)
        except ValueError:
            return self._preview_unavailable(
                variant,
                PreviewUnavailableReason.INVALID_VARIANT,
            )
        try:
            with JobStore(self._job_database) as store:
                job = store.get_job(identifier)
        except KeyError:
            return self._preview_unavailable(
                kind.value,
                PreviewUnavailableReason.UNKNOWN_JOB,
            )
        return build_job_preview(job, kind).as_dict()

    def open_job_output(self, identifier: str) -> bool:
        try:
            with JobStore(self._job_database) as store:
                job = store.get_job(identifier)
        except KeyError:
            return False
        if job.output is None:
            return False
        target = job.output.parent.resolve()
        expected = (job.source.parent / "车牌已消除").resolve()
        if target != expected or not target.is_dir():
            return False
        os.startfile(target)
        return True

    def open_output(self, value: str) -> bool:
        path = Path(value)
        target = path if path.is_dir() else path.parent
        if not target.exists() or target.name != "车牌已消除":
            return False
        os.startfile(target)
        return True

    def _on_drop(self, event: dict[str, Any]) -> None:
        files = event.get("dataTransfer", {}).get("files", [])
        paths = [
            str(file["pywebviewFullPath"])
            for file in files
            if file.get("pywebviewFullPath")
        ]
        if paths:
            self.start_batch(paths)


class _SmokeApi(DesktopApi):
    """Desktop API variant that closes after the frontend initializes."""

    def __init__(self, ready: threading.Event) -> None:
        super().__init__()
        self._smoke_ready = ready

    def frontend_ready(self) -> bool:
        self._smoke_ready.set()
        if self._window is not None:
            threading.Timer(0.2, self._window.destroy).start()
        return True


def smoke() -> int:
    """Load the local frontend and Python bridge, then exit automatically."""

    loaded = threading.Event()
    bridge_ready = threading.Event()
    api = _SmokeApi(bridge_ready)
    window = webview.create_window(
        "消除车牌 · 启动检查",
        url=str(frontend_directory() / "index.html"),
        js_api=api,
        width=1040,
        height=680,
        min_size=(1040, 680),
        background_color="#0C111B",
    )
    if window is None:
        return 1
    api._bind_window(window)

    def mark_loaded() -> None:
        loaded.set()

    window.events.loaded += mark_loaded
    webview.start(gui="edgechromium", debug=False, private_mode=True)
    return 0 if loaded.is_set() and bridge_ready.is_set() else 1


def launch() -> int:
    index = frontend_directory() / "index.html"
    if not index.is_file():
        raise RuntimeError(f"frontend assets are missing: {index}")
    api = DesktopApi()
    window = webview.create_window(
        "消除车牌",
        url=str(index),
        js_api=api,
        width=1280,
        height=820,
        min_size=(1040, 680),
        background_color="#0C111B",
        text_select=True,
    )
    if window is None:
        raise RuntimeError("failed to create desktop window")
    api._bind_window(window)

    def attach_drop_handler() -> None:
        drop_zone = window.dom.get_element("#drop-zone")
        if drop_zone is not None:
            drop_zone.events.drop += api._on_drop

    window.events.loaded += attach_drop_handler
    # Spec v0.3.0 §9.2: stop the watch service and drain the batch when the
    # user closes the window so no daemon threads outlive the app.
    window.events.closing += api.shutdown
    webview.start(gui="edgechromium", debug=False, private_mode=True)
    return 0
