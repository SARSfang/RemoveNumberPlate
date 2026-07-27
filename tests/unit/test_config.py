from pathlib import Path

import pytest

from app.config import AppPaths, ProcessingPreset


def test_default_paths_keep_models_in_project_and_state_outside_it() -> None:
    paths = AppPaths.default()

    assert paths.model_manifest == paths.project_root / "models" / "manifest.json"
    assert paths.job_database == paths.data_dir / "jobs.sqlite3"
    assert paths.data_dir != paths.project_root


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("auto_confidence", 1.1),
        ("tile_size", 128),
        ("tile_overlap", 1.0),
        ("context_scale", 1.0),
    ],
)
def test_processing_preset_rejects_unsafe_values(field: str, value: float) -> None:
    values: dict[str, str | float | int] = {
        "name": "test",
        "auto_confidence": 0.5,
        "tile_size": 1024,
        "tile_overlap": 0.2,
        "context_scale": 4.0,
    }
    values[field] = value

    with pytest.raises(ValueError):
        ProcessingPreset(**values)  # type: ignore[arg-type]


def test_paths_accept_isolated_test_locations(tmp_path: Path) -> None:
    paths = AppPaths(
        project_root=tmp_path,
        models_dir=tmp_path / "models",
        model_manifest=tmp_path / "models" / "manifest.json",
        data_dir=tmp_path / "data",
        log_dir=tmp_path / "logs",
        job_database=tmp_path / "data" / "jobs.sqlite3",
    )

    assert paths.project_root == tmp_path
