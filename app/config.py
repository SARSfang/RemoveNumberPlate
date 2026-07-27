"""Application configuration and filesystem locations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_data_path, user_log_path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = PROJECT_ROOT / "models"
MODEL_MANIFEST_PATH = MODELS_DIR / "manifest.json"


@dataclass(frozen=True, slots=True)
class ProcessingPreset:
    """User-facing processing preset.

    Model-specific thresholds remain outside the GUI and can be revised after
    the M1 benchmark without changing consumers of this object.
    """

    name: str
    auto_confidence: float
    tile_size: int
    tile_overlap: float
    context_scale: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.auto_confidence <= 1.0:
            raise ValueError("auto_confidence must be between 0 and 1")
        if self.tile_size < 256:
            raise ValueError("tile_size must be at least 256 pixels")
        if not 0.0 <= self.tile_overlap < 1.0:
            raise ValueError("tile_overlap must be between 0 and 1")
        if self.context_scale <= 1.0:
            raise ValueError("context_scale must be greater than 1")


PRESETS: dict[str, ProcessingPreset] = {
    "speed": ProcessingPreset("speed", 0.70, 1280, 0.15, 3.0),
    "balanced": ProcessingPreset("balanced", 0.60, 1024, 0.20, 4.0),
    "quality": ProcessingPreset("quality", 0.50, 896, 0.25, 5.0),
}


@dataclass(frozen=True, slots=True)
class AppPaths:
    """Resolved paths for immutable assets and mutable application data."""

    project_root: Path
    models_dir: Path
    model_manifest: Path
    data_dir: Path
    log_dir: Path
    job_database: Path

    @classmethod
    def default(cls) -> AppPaths:
        data_dir = user_data_path("RemoveNumberPlate", "SARSfang", ensure_exists=False)
        log_dir = user_log_path("RemoveNumberPlate", "SARSfang", ensure_exists=False)
        return cls(
            project_root=PROJECT_ROOT,
            models_dir=MODELS_DIR,
            model_manifest=MODEL_MANIFEST_PATH,
            data_dir=data_dir,
            log_dir=log_dir,
            job_database=data_dir / "jobs.sqlite3",
        )
