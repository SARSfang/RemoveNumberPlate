"""Release-grade model and storage preflight checks."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from app.infrastructure.model_registry import ModelManifestError, load_manifest

MIN_FREE_BYTES = 512 * 1024 * 1024
MIN_OUTPUT_BYTES_PER_IMAGE = 1024 * 1024
OUTPUT_SIZE_MULTIPLIER = 2


@dataclass(frozen=True, slots=True)
class ModelState:
    model_id: str
    ready: bool


@dataclass(frozen=True, slots=True)
class ModelReadiness:
    ready: bool
    states: tuple[ModelState, ...]
    issue: str | None = None


@dataclass(frozen=True, slots=True)
class StorageReadiness:
    ready: bool
    required_bytes: int
    free_bytes: int
    issue: str | None = None


def inspect_models(manifest_path: Path, models_dir: Path) -> ModelReadiness:
    """Verify every enabled artifact without allowing manifest failures to crash UI."""

    try:
        artifacts = tuple(
            artifact for artifact in load_manifest(manifest_path) if artifact.enabled
        )
    except (ModelManifestError, OSError, ValueError) as error:
        return ModelReadiness(
            False,
            (),
            f"模型清单无法读取：{type(error).__name__}: {error}",
        )
    if not artifacts:
        return ModelReadiness(False, (), "模型清单中没有启用的处理模型。")
    states = tuple(
        ModelState(
            artifact.model_id,
            artifact.verify(models_dir / artifact.filename),
        )
        for artifact in artifacts
    )
    if all(state.ready for state in states):
        return ModelReadiness(True, states)
    failed = "、".join(state.model_id for state in states if not state.ready)
    return ModelReadiness(False, states, f"模型缺失或校验失败：{failed}")


def inspect_storage(sources: list[Path]) -> StorageReadiness:
    """Estimate output space per volume and keep a safety reserve."""

    if not sources:
        return StorageReadiness(False, 0, 0, "没有可处理的照片。")
    volume_paths: dict[str, Path] = {}
    volume_requirements: dict[str, int] = {}
    try:
        for source in sources:
            resolved = source.resolve()
            key = resolved.anchor.casefold() or str(resolved.parent).casefold()
            volume_paths.setdefault(key, resolved.parent)
            estimated = max(
                resolved.stat().st_size * OUTPUT_SIZE_MULTIPLIER,
                MIN_OUTPUT_BYTES_PER_IMAGE,
            )
            volume_requirements[key] = volume_requirements.get(key, 0) + estimated
    except OSError as error:
        return StorageReadiness(
            False,
            0,
            0,
            f"无法检查照片或磁盘空间：{type(error).__name__}: {error}",
        )

    total_required = 0
    minimum_free = 0
    try:
        for key, estimated in volume_requirements.items():
            required = max(estimated, MIN_FREE_BYTES)
            free = shutil.disk_usage(volume_paths[key]).free
            total_required += required
            minimum_free = free if minimum_free == 0 else min(minimum_free, free)
            if free < required:
                required_gib = required / (1024**3)
                free_gib = free / (1024**3)
                return StorageReadiness(
                    False,
                    total_required,
                    minimum_free,
                    f"输出磁盘空间不足：至少需要 {required_gib:.2f} GiB，"
                    f"当前可用 {free_gib:.2f} GiB。",
                )
    except OSError as error:
        return StorageReadiness(
            False,
            total_required,
            minimum_free,
            f"无法检查输出磁盘空间：{type(error).__name__}: {error}",
        )
    return StorageReadiness(True, total_required, minimum_free)
