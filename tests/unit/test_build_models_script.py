import hashlib
import io
import json
import tarfile
from pathlib import Path

import pytest

from scripts import build_models as model_builder
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


def test_direct_download_can_use_working_candidate_in_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = b"downloaded-model"
    filename = "model.onnx"
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "model_id": "direct",
                        "enabled": True,
                        "filename": filename,
                        "sha256": hashlib.sha256(payload).hexdigest(),
                        "source_url": "https://example.invalid/model.onnx",
                        "build": {"kind": "download"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    def fake_download(_url: str, destination: Path) -> None:
        destination.write_bytes(payload)

    monkeypatch.setattr(model_builder, "download", fake_download)
    output = tmp_path / "output"
    model_builder.build_models(manifest, output, None, force=True)

    assert (output / filename).read_bytes() == payload
