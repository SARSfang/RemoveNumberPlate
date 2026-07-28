import io
import tarfile
from pathlib import Path

import pytest

from scripts.build_models import safe_extract_tar


def test_safe_extract_tar_extracts_regular_file(tmp_path: Path) -> None:
    archive = tmp_path / "model.tar"
    with tarfile.open(archive, "w") as bundle:
        value = b"model"
        info = tarfile.TarInfo("model/inference.json")
        info.size = len(value)
        bundle.addfile(info, io.BytesIO(value))

    destination = tmp_path / "out"
    destination.mkdir()
    safe_extract_tar(archive, destination)

    assert (destination / "model" / "inference.json").read_bytes() == b"model"


def test_safe_extract_tar_rejects_path_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.tar"
    with tarfile.open(archive, "w") as bundle:
        info = tarfile.TarInfo("../escape")
        info.size = 1
        bundle.addfile(info, io.BytesIO(b"x"))

    destination = tmp_path / "out"
    destination.mkdir()
    with pytest.raises(RuntimeError, match="unsafe archive member"):
        safe_extract_tar(archive, destination)
