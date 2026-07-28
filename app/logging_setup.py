"""Privacy-aware rotating application logging and fatal error reporting."""

from __future__ import annotations

import ctypes
import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType

from app.config import AppPaths

LOGGER_NAME = "remove_number_plate"


def configure_logging(paths: AppPaths | None = None) -> Path:
    resolved = paths or AppPaths.default()
    resolved.log_dir.mkdir(parents=True, exist_ok=True)
    log_path = resolved.log_dir / "application.log"
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    if not any(
        isinstance(handler, RotatingFileHandler)
        and Path(handler.baseFilename) == log_path
        for handler in logger.handlers
    ):
        handler = RotatingFileHandler(
            log_path,
            maxBytes=2 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(threadName)s %(name)s: %(message)s"
            )
        )
        logger.addHandler(handler)
    return log_path


def install_exception_hooks(log_path: Path) -> None:
    logger = logging.getLogger(LOGGER_NAME)

    def handle_exception(
        exception_type: type[BaseException],
        exception: BaseException,
        traceback: TracebackType | None,
    ) -> None:
        logger.critical(
            "Unhandled application exception",
            exc_info=(exception_type, exception, traceback),
        )
        show_fatal_error(
            "消除车牌遇到未处理的错误。\n\n"
            f"诊断日志已保存到：\n{log_path}\n\n"
            "请重新启动应用；如果问题持续，请导出诊断包。"
        )

    def handle_thread_exception(arguments: threading.ExceptHookArgs) -> None:
        if arguments.exc_value is None:
            logger.error("Worker thread exited without an exception value")
            return
        logger.error(
            "Unhandled worker exception",
            exc_info=(arguments.exc_type, arguments.exc_value, arguments.exc_traceback),
        )

    sys.excepthook = handle_exception
    threading.excepthook = handle_thread_exception


def show_fatal_error(message: str) -> None:
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(0, message, "消除车牌", 0x10)
    else:
        print(message, file=sys.stderr)
