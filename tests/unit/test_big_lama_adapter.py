import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from app.infrastructure.big_lama_inpainter import BigLamaInpainter
from app.infrastructure.migan_inpainter import InpainterError


def worker_adapter():
    item = BigLamaInpainter.__new__(BigLamaInpainter)
    item._model = Path("model.pt")
    item._python = Path(sys.executable)
    item._worker = Path("worker.py")
    item._executable = None
    return item


def test_missing_or_corrupt_model_is_rejected(tmp_path):
    with pytest.raises(InpainterError, match="未安装"):
        BigLamaInpainter(tmp_path)
    (tmp_path / "big-lama.pt").write_bytes(b"corrupt")
    with pytest.raises(InpainterError, match="校验失败"):
        BigLamaInpainter(tmp_path)


def test_timeout_and_failed_worker_clean_temporary_files(monkeypatch):
    seen = []
    def timeout(command, **kwargs):
        seen.append(Path(command[-2]).parent)
        raise subprocess.TimeoutExpired(command, 180)
    monkeypatch.setattr(subprocess, "run", timeout)
    image = np.zeros((64, 64, 3), dtype=np.uint8)
    with pytest.raises(InpainterError, match="超时"):
        worker_adapter().generate_crop(image, image[:, :, 0], 1024)
    assert seen and not seen[0].exists()
    def failed(command, **kwargs):
        return subprocess.CompletedProcess(command, 1, "", "CUDA out of memory")
    monkeypatch.setattr(subprocess, "run", failed)
    with pytest.raises(InpainterError, match="内存不足"):
        worker_adapter().generate_crop(image, image[:, :, 0], 1024)


def test_invalid_worker_output_cannot_be_saved(monkeypatch):
    image = np.zeros((64, 64, 3), dtype=np.uint8)
    def wrong_shape(command, **kwargs):
        np.save(command[-2], np.zeros((1, 1, 3), dtype=np.uint8))
        return subprocess.CompletedProcess(command, 0, "cpu", "")
    monkeypatch.setattr(subprocess, "run", wrong_shape)
    with pytest.raises(InpainterError, match="尺寸"):
        worker_adapter().generate_crop(image, image[:, :, 0], 1024)
