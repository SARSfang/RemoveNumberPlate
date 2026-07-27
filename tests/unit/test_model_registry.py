import hashlib
import json
from pathlib import Path

import pytest

from app.infrastructure.model_registry import ModelManifestError, load_manifest


def _write_manifest(path: Path, model: dict[str, object]) -> None:
    path.write_text(
        json.dumps({"schema_version": 1, "models": [model]}),
        encoding="utf-8",
    )


def _model(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "model_id": "detector",
        "version": "1",
        "filename": "model.bin",
        "sha256": "0" * 64,
        "source_url": "https://example.com/model.bin",
        "homepage": "https://example.com",
        "format": "test",
        "software_license": "Apache-2.0",
        "weights_terms": "test-only",
        "enabled": True,
    }
    value.update(overrides)
    return value


def test_manifest_loads_and_verifies_artifact(tmp_path: Path) -> None:
    artifact_path = tmp_path / "model.bin"
    artifact_path.write_bytes(b"verified model")
    digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, _model(sha256=digest))

    artifact = load_manifest(manifest_path)[0]

    assert artifact.verify(artifact_path)


def test_manifest_rejects_path_traversal(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, _model(filename="../model.bin"))

    with pytest.raises(ModelManifestError, match="must not contain a path"):
        load_manifest(manifest_path)


def test_disabled_candidate_can_omit_url_and_hash(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(
        manifest_path,
        _model(enabled=False, source_url="", sha256=""),
    )

    artifact = load_manifest(manifest_path)[0]

    assert not artifact.enabled
    assert not artifact.verify(tmp_path / "missing.bin")
