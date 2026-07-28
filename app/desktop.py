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
from pathlib import Path
from typing import Any

import webview

from app.cli import build_manual_processor, build_processor
from app.config import PRESETS, AppPaths
from app.core.batch import Processor
from app.core.image_io import discover_images, load_image
from app.core.job_preview import (
    THUMBNAIL_BOUNDS,
    THUMBNAIL_QUALITY,
    JobPreview,
    PreviewKind,
    PreviewUnavailableReason,
    build_job_preview,
)
from app.core.job_store import JobStore, prepare_job_database
from app.core.manual_mask import build_manual_mask
from app.core.pipeline import ManualMaskProcessor
from app.domain.job import JobStatus
from app.domain.result import ProcessingResult
from app.infrastructure.device_probe import probe_device
from app.infrastructure.webview2 import detect_webview2_version
from app.release_readiness import inspect_models, inspect_storage
from app.settings import SettingsStore, UserSettings
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


def frontend_directory() -> Path:
    """Resolve bundled static assets in development and PyInstaller builds."""

    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return bundle_root / "app" / "web"


class BatchService:
    """Own model instances in one worker thread and publish immutable events."""

    def __init__(
        self,
        event_sink: EventSink,
        processor_factory: ProcessorFactory | None = None,
        *,
        job_database: Path | None = None,
    ) -> None:
        self._event_sink = event_sink
        self._processor_factory = processor_factory or (lambda: build_processor(0.60))
        self._job_database = job_database or AppPaths.default().job_database
        self._condition = threading.Condition()
        self._busy = False
        self._paused = False
        self._cancelled = False
        self._thread: threading.Thread | None = None
        self._processor: Processor | None = None

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
            if not self._busy:
                return False
            self._cancelled = True
            self._paused = False
            self._condition.notify_all()
        return True

    def wait(self, timeout: float = 10.0) -> bool:
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
        return not self.busy

    def _emit(self, name: str, payload: dict[str, object]) -> None:
        self._event_sink(name, payload)

    def _ready_for_next(self) -> bool:
        with self._condition:
            while self._paused and not self._cancelled:
                self._condition.wait()
            return not self._cancelled

    def _finish(self, cancelled: bool) -> None:
        with self._condition:
            self._busy = False
            self._paused = False
        self._emit("batch_finished", {"cancelled": cancelled})

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
            self._settings.preset
        )
        self._service = BatchService(
            self._send_event,
            default_factory,
            job_database=self._job_database,
        )
        self._manual_processor_factory = manual_processor_factory or build_manual_processor
        self._manual_processor: ManualMaskProcessor | None = None
        self._review_lock = threading.Lock()
        self._review_busy = False

    @staticmethod
    def _processor_factory_for(preset: str) -> ProcessorFactory:
        confidence = PRESETS[preset].auto_confidence
        return lambda: build_processor(confidence)

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
            "webview2_version": detect_webview2_version() or "未检测到",
            "preset": self._settings.preset,
        }

    def set_preset(self, preset: str) -> dict[str, object]:
        if preset not in PRESETS:
            return {"accepted": False, "message": "未知的处理预设。"}
        if not self._service.replace_processor_factory(
            self._processor_factory_for(preset)
        ):
            return {
                "accepted": False,
                "message": "当前批次运行中，请在处理结束后更改预设。",
            }
        self._settings = UserSettings(preset=preset)
        self._settings_store.save(self._settings)
        return {"accepted": True, "message": "处理预设已保存。"}

    def list_history(self, limit: int = 100) -> list[dict[str, object]]:
        safe_limit = max(1, min(int(limit), 500))
        with JobStore(self._job_database) as store:
            jobs = store.list_jobs(limit=safe_limit)
        return [
            {
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
            }
            for job in jobs
        ]

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
                    "x1": detection.box.x1,
                    "y1": detection.box.y1,
                    "x2": detection.box.x2,
                    "y2": detection.box.y2,
                    "confidence": detection.confidence,
                }
                for detection in job.detections
            ],
            "commands": commands,
            "risks": [risk.value for risk in job.risks],
        }

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
                store.record_mask_revision(identifier, commands)
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
                store.record_result(identifier, result)
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
    webview.start(gui="edgechromium", debug=False, private_mode=True)
    return 0
