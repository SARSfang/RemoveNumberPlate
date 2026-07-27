import hashlib
import json
from pathlib import Path
from typing import cast

from scripts.verify_models import build_report


def test_build_report_verifies_enabled_model(tmp_path: Path) -> None:
    artifact = tmp_path / "model.bin"
    artifact.write_bytes(b"model")
    digest = hashlib.sha256(b"model").hexdigest()
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "models": [
                    {
                        "model_id": "test",
                        "version": "1",
                        "filename": "model.bin",
                        "sha256": digest,
                        "source_url": "https://example.com/model.bin",
                        "homepage": "https://example.com",
                        "format": "test",
                        "software_license": "Apache-2.0",
                        "weights_terms": "test",
                        "enabled": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    report = build_report(manifest, tmp_path)
    models = cast(list[dict[str, object]], report["models"])

    assert models[0]["verified"] is True
