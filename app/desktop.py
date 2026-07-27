"""Lightweight WebView2 desktop shell and background batch service."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import webview

from app.cli import build_processor
from app.config import AppPaths
from app.core.batch import Processor
from app.core.image_io import discover_images
from app.core.job_store import JobStore
from app.domain.job import JobStatus
from app.domain.result import ProcessingResult
from app.infrastructure.device_probe import probe_device
from app.infrastructure.model_registry import load_manifest

EventSink = Callable[[str, dict[str, object]], None]
ProcessorFactory = Callable[[], Processor]


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

    @property
    def busy(self) -> bool:
        with self._condition:
            return self._busy

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
            processor = self._processor_factory()
            with JobStore(self._job_database) as store:
                jobs = [(store.create_job(source), source) for source in sources]
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
                            "source": str(source),
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
                            "source": str(source),
                            "name": source.name,
                            "index": index,
                            "total": len(jobs),
                            "status": result.status.value,
                            "elapsed": round(result.elapsed_seconds, 3),
                            "output": str(result.output) if result.output else None,
                            "risks": [risk.value for risk in result.risks],
                            "error": result.error,
                        },
                    )
        except Exception as error:
            self._emit(
                "fatal_error",
                {"message": f"{type(error).__name__}: {error}"},
            )
            self._finish(False)
            return
        self._finish(False)


class DesktopApi:
    """Small allow-listed API exposed to the bundled local frontend."""

    def __init__(self, processor_factory: ProcessorFactory | None = None) -> None:
        self._window: webview.Window | None = None
        self._service = BatchService(self._send_event, processor_factory)

    def bind_window(self, window: webview.Window) -> None:
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
        model_states = [
            {
                "id": artifact.model_id,
                "ready": artifact.verify(paths.models_dir / artifact.filename),
            }
            for artifact in load_manifest(paths.model_manifest)
            if artifact.enabled
        ]
        with JobStore(paths.job_database) as store:
            counts = store.counts()
        return {
            "gpu": device.gpu_name or "未检测到 NVIDIA GPU",
            "cuda_available": device.gpu_name is not None,
            "models_ready": all(value["ready"] for value in model_states),
            "model_states": model_states,
            "history_counts": counts,
            "runtime": "GPU 检测 + CPU LaMa 修复",
        }

    def frontend_ready(self) -> bool:
        """Acknowledge that assets and the JS bridge completed initialization."""

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

    def open_output(self, value: str) -> bool:
        path = Path(value)
        target = path if path.is_dir() else path.parent
        if not target.exists() or target.name != "车牌已消除":
            return False
        os.startfile(target)
        return True

    def on_drop(self, event: dict[str, Any]) -> None:
        files = event.get("dataTransfer", {}).get("files", [])
        paths = [
            str(file["pywebviewFullPath"])
            for file in files
            if file.get("pywebviewFullPath")
        ]
        if paths:
            self.start_batch(paths)


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
    api.bind_window(window)

    def attach_drop_handler() -> None:
        drop_zone = window.dom.get_element("#drop-zone")
        if drop_zone is not None:
            drop_zone.events.drop += api.on_drop

    window.events.loaded += attach_drop_handler
    webview.start(gui="edgechromium", debug=False, private_mode=True)
    return 0
