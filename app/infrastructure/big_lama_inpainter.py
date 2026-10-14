"""Optional Big-LaMa worker isolated from the standard ONNX environment."""
from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from app.infrastructure.migan_inpainter import InpainterError

LOGGER = logging.getLogger("remove_number_plate.repair")


class BigLamaInpainter:
    def __init__(self, models_dir: Path) -> None:
        self._model = models_dir / "big-lama.pt"
        if not self._model.is_file():
            raise InpainterError("未安装 Big-LaMa 高清模型")
        # Published checksum from the IOPaint maintainer's model adapter.
        digest = hashlib.sha256()
        with self._model.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != "344c77bbcb158f17dd143070d1e789f38a66c04202311ae3a258ef66667a9ea9":
            raise InpainterError("Big-LaMa 模型校验失败，请重新安装高清组件")
        root = models_dir.parent
        workers = [root / "hd-runtime" / "big-lama-worker.exe",
                   root.parent / "hd-runtime" / "big-lama-worker.exe",
                   root / "hd-runtime" / "big-lama-worker" / "big-lama-worker.exe",
                   root.parent / "hd-runtime" / "big-lama-worker" / "big-lama-worker.exe"]
        self._executable = next((path for path in workers if path.is_file()), None)
        candidates = [root / "hd-runtime" / "Scripts" / "python.exe",
                      root / ".venv-hd" / "Scripts" / "python.exe"]
        self._python = next((path for path in candidates if path.is_file()), None)
        if self._python is None and self._executable is None:
            raise InpainterError("未安装高清修复运行组件")
        self._worker = Path(__file__).with_name("big_lama_worker.py")
        if self._executable is None and not self._worker.is_file():
            raise InpainterError("高清修复工作程序缺失")

    def generate_crop(
        self, image: NDArray[np.uint8], mask: NDArray[np.uint8], max_side: int,
    ) -> NDArray[np.uint8]:
        with tempfile.TemporaryDirectory(prefix="plate-hd-") as directory:
            folder = Path(directory)
            source, target = folder / "input.npz", folder / "output.npy"
            np.savez(source, image=image, mask=mask)
            try:
                command = ([str(self._executable)] if self._executable is not None
                           else [str(self._python), str(self._worker)])
                completed = subprocess.run(
                    [*command, str(self._model), str(source), str(target), str(max_side)],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                    timeout=180, check=False,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                    env={**os.environ, "PYTHONUTF8": "1", "PYINSTALLER_RESET_ENVIRONMENT": "1"},
                )
            except subprocess.TimeoutExpired as error:
                raise InpainterError("高清修复超时，请降低高清处理上限") from error
            except OSError as error:
                LOGGER.exception("HD worker could not start")
                raise InpainterError("高清修复组件无法启动，请重新安装高清组件") from error
            if completed.returncode != 0:
                LOGGER.error("HD worker failed (%s): %s", completed.returncode, completed.stderr)
                reason = ("高清修复内存不足，请降低高清处理上限"
                          if "out of memory" in completed.stderr.lower()
                          else "高清修复组件运行失败，请导出诊断日志")
                raise InpainterError(reason)
            if not target.is_file():
                raise InpainterError("高清修复未生成结果")
            try:
                result = np.load(target, allow_pickle=False)
            except (OSError, ValueError) as error:
                raise InpainterError("高清修复输出无法读取") from error
            if result.shape != image.shape or result.dtype != np.uint8:
                raise InpainterError("高清修复输出尺寸或格式无效")
            return np.asarray(result, dtype=np.uint8)
