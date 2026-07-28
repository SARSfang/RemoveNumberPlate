from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import release_readiness
from app.release_readiness import inspect_models, inspect_storage


def _manifest(path: Path, filename: str, payload: bytes) -> Path:
    manifest = path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "models": [
                    {
                        "model_id": "model",
                        "version": "1",
                        "filename": filename,
                        "sha256": hashlib.sha256(payload).hexdigest(),
                        "source_url": "https://example.invalid/model",
                        "homepage": "https://example.invalid",
                        "format": "onnx",
                        "software_license": "Apache-2.0",
                        "weights_terms": "test",
                        "enabled": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return manifest


def test_model_preflight_reports_verified_artifact(tmp_path: Path) -> None:
    payload = b"model"
    (tmp_path / "model.onnx").write_bytes(payload)

    readiness = inspect_models(
        _manifest(tmp_path, "model.onnx", payload),
        tmp_path,
    )

    assert readiness.ready
    assert readiness.issue is None
    assert readiness.states[0].ready


def test_model_preflight_turns_manifest_error_into_actionable_state(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{", encoding="utf-8")

    readiness = inspect_models(manifest, tmp_path)

    assert not readiness.ready
    assert readiness.states == ()
    assert readiness.issue is not None
    assert "模型清单无法读取" in readiness.issue


def test_storage_preflight_rejects_volume_below_safety_reserve(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "photo.jpg"
    source.write_bytes(b"image")
    monkeypatch.setattr(
        release_readiness.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(free=128 * 1024 * 1024),
    )

    readiness = inspect_storage([source])

    assert not readiness.ready
    assert readiness.issue is not None
    assert "磁盘空间不足" in readiness.issue
