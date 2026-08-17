"""Unit tests for ProjectStore and ProjectPreset."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from app.core.exif_writer import ExifConfig
from app.core.job_store import JobStore
from app.core.project_store import (
    OutputDirectoryRule,
    ProjectPreset,
    ProjectStore,
)
from app.core.watermark import WatermarkConfig
from app.settings import PostProcessConfig


def _init_database(tmp_path: Path) -> Path:
    """Initialise a jobs database with the current schema (v7)."""
    database = tmp_path / "jobs.sqlite3"
    with JobStore(database):
        pass
    return database


def test_create_project(tmp_path: Path) -> None:
    """create_project should persist and return the new project."""
    database = _init_database(tmp_path)
    with ProjectStore(database) as store:
        project = store.create_project(
            "客户A-商拍",
            preset="balanced",
            mask_margin_ratio=0.35,
            post_process_config=PostProcessConfig(
                enabled=True,
                naming_template="{client}_{seq:03}{ext}",
                watermark=WatermarkConfig(enabled=True, text="© acme"),
                exif=ExifConfig(enabled=True, artist="studio"),
            ),
            output_directory_rule=OutputDirectoryRule(
                mode="project_subfolder", subfolder_name="已消除"
            ),
        )

        assert project.id
        assert project.name == "客户A-商拍"
        assert project.preset == "balanced"
        assert project.mask_margin_ratio == 0.35
        assert project.created_at
        assert project.last_used_at == ""
        assert project.post_process_config.enabled is True
        assert project.output_directory_rule.mode == "project_subfolder"

        # Re-open and verify persistence
        fetched = store.get_project(project.id)
        assert fetched is not None
        assert fetched.name == "客户A-商拍"
        assert fetched.preset == "balanced"
        assert fetched.mask_margin_ratio == 0.35
        assert fetched.post_process_config.enabled is True
        assert fetched.post_process_config.watermark.text == "© acme"
        assert fetched.output_directory_rule.subfolder_name == "已消除"


def test_list_projects_ordered_by_last_used(tmp_path: Path) -> None:
    """list_projects should order by last_used_at DESC, name ASC."""
    database = _init_database(tmp_path)
    with ProjectStore(database) as store:
        alpha = store.create_project("Alpha")
        beta = store.create_project("Beta")
        gamma = store.create_project("Gamma")

        # Touch Alpha first, then Beta (Beta is more recent)
        store.touch_last_used(alpha.id)
        time.sleep(0.01)
        store.touch_last_used(beta.id)

        projects = store.list_projects()

        # Beta (most recent) > Alpha (older) > Gamma (never used)
        assert len(projects) == 3
        assert projects[0].id == beta.id
        assert projects[1].id == alpha.id
        assert projects[2].id == gamma.id


def test_get_project(tmp_path: Path) -> None:
    """get_project should return the project by id."""
    database = _init_database(tmp_path)
    with ProjectStore(database) as store:
        created = store.create_project("Test Project", preset="speed")

        fetched = store.get_project(created.id)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.name == "Test Project"
        assert fetched.preset == "speed"


def test_get_project_not_found(tmp_path: Path) -> None:
    """get_project with unknown id should return None."""
    database = _init_database(tmp_path)
    with ProjectStore(database) as store:
        assert store.get_project("nonexistent-id") is None


def test_update_project(tmp_path: Path) -> None:
    """update_project should modify fields and persist changes."""
    database = _init_database(tmp_path)
    with ProjectStore(database) as store:
        created = store.create_project("Original", preset="balanced")

        updated = store.update_project(
            created.id,
            name="Renamed",
            preset="quality",
            mask_margin_ratio=0.50,
            post_process_config=PostProcessConfig(enabled=True),
            output_directory_rule=OutputDirectoryRule(
                mode="fixed_directory", fixed_directory="D:/output"
            ),
        )

        assert updated.name == "Renamed"
        assert updated.preset == "quality"
        assert updated.mask_margin_ratio == 0.50
        assert updated.post_process_config.enabled is True
        assert updated.output_directory_rule.mode == "fixed_directory"
        assert updated.output_directory_rule.fixed_directory == "D:/output"

        # Verify persistence
        fetched = store.get_project(created.id)
        assert fetched is not None
        assert fetched.name == "Renamed"
        assert fetched.preset == "quality"
        assert fetched.mask_margin_ratio == 0.50


def test_update_project_not_found(tmp_path: Path) -> None:
    """update_project with unknown id should raise KeyError."""
    database = _init_database(tmp_path)
    with ProjectStore(database) as store, pytest.raises(KeyError):
        store.update_project("nonexistent-id", name="X")


def test_delete_project(tmp_path: Path) -> None:
    """delete_project should remove the project and return True."""
    database = _init_database(tmp_path)
    with ProjectStore(database) as store:
        created = store.create_project("To Delete")

        assert store.delete_project(created.id) is True
        assert store.get_project(created.id) is None


def test_delete_project_not_found(tmp_path: Path) -> None:
    """delete_project with unknown id should return False."""
    database = _init_database(tmp_path)
    with ProjectStore(database) as store:
        assert store.delete_project("nonexistent-id") is False


def test_touch_last_used(tmp_path: Path) -> None:
    """touch_last_used should set last_used_at to a current timestamp."""
    database = _init_database(tmp_path)
    with ProjectStore(database) as store:
        created = store.create_project("Touch Me")
        assert created.last_used_at == ""

        store.touch_last_used(created.id)

        fetched = store.get_project(created.id)
        assert fetched is not None
        assert fetched.last_used_at != ""
        # CI runners can execute create_project and touch_last_used within
        # the same microsecond, so only require last_used_at >= created_at.
        assert fetched.last_used_at >= created.created_at


def test_project_preset_validation() -> None:
    """ProjectPreset should reject empty name or id."""
    with pytest.raises(ValueError, match="project name must not be empty"):
        ProjectPreset(id="some-id", name="   ")

    with pytest.raises(ValueError, match="project id must not be empty"):
        ProjectPreset(id="", name="Valid Name")

    with pytest.raises(ValueError, match="project id must not be empty"):
        ProjectPreset(id="   ", name="Valid Name")


def test_output_directory_rule_modes() -> None:
    """OutputDirectoryRule should validate mode and fixed_directory requirement."""

    # Default mode is beside_source
    rule = OutputDirectoryRule()
    assert rule.mode == "beside_source"

    # project_subfolder mode
    rule_sub = OutputDirectoryRule(mode="project_subfolder", subfolder_name="out")
    assert rule_sub.mode == "project_subfolder"

    # fixed_directory mode requires fixed_directory
    rule_fixed = OutputDirectoryRule(mode="fixed_directory", fixed_directory="D:/out")
    assert rule_fixed.mode == "fixed_directory"

    # Invalid mode
    with pytest.raises(ValueError, match="unknown output directory mode"):
        OutputDirectoryRule(mode="invalid_mode")

    # fixed_directory without fixed_directory value
    with pytest.raises(ValueError, match="fixed_directory mode requires"):
        OutputDirectoryRule(mode="fixed_directory", fixed_directory="")

    with pytest.raises(ValueError, match="fixed_directory mode requires"):
        OutputDirectoryRule(mode="fixed_directory", fixed_directory="   ")
