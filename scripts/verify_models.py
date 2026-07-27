"""Verify pinned model artifacts without importing an inference framework."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from app.config import AppPaths
from app.infrastructure.device_probe import probe_device
from app.infrastructure.model_registry import load_manifest


def build_report(manifest_path: Path, models_dir: Path) -> dict[str, object]:
    artifacts = load_manifest(manifest_path)
    device = probe_device()
    model_reports: list[dict[str, object]] = []
    for artifact in artifacts:
        artifact_path = models_dir / artifact.filename
        model_reports.append(
            {
                "model_id": artifact.model_id,
                "enabled": artifact.enabled,
                "exists": artifact_path.is_file(),
                "verified": artifact.verify(artifact_path),
                "path": str(artifact_path),
                "source_url": artifact.source_url,
                "format": artifact.format,
            }
        )
    return {
        "gpu": {
            "name": device.gpu_name,
            "driver": device.driver_version,
            "memory_mib": device.memory_mib,
        },
        "onnx_providers": list(device.onnx_providers),
        "models": model_reports,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--models-dir", type=Path)
    arguments = parser.parse_args()

    paths = AppPaths.default()
    manifest_path = arguments.manifest or paths.model_manifest
    models_dir = arguments.models_dir or paths.models_dir
    report = build_report(manifest_path, models_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    models = cast(list[dict[str, object]], report["models"])
    enabled = [model for model in models if model["enabled"]]
    return 0 if enabled and all(model["verified"] for model in enabled) else 1


if __name__ == "__main__":
    raise SystemExit(main())
