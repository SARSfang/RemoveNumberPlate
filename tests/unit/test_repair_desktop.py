from pathlib import Path

import pytest

from app import desktop
from app.core.adjustment_session import AdjustmentSessionManager
from app.core.repair_config import RepairConfig
from app.desktop import DesktopApi
from app.domain.result import ProcessingResult
from app.settings import SettingsStore


class IdleProcessor:
    def process(self, source):
        return ProcessingResult(None, 0)


def test_repair_settings_invalidate_preview_and_persist(tmp_path: Path):
    api = DesktopApi(lambda: IdleProcessor(), job_database=tmp_path / "jobs.sqlite3")
    api._settings_store = SettingsStore(tmp_path / "settings.json")
    api._manual_processor = object()
    generation = api._adjustments.begin("job-1", "base", [])
    cache = api._adjustments.cache_path(generation, ".png")
    cache.write_bytes(b"preview")
    session = api._adjustments.complete(generation, cache, width=1, height=1, elapsed_seconds=0)
    assert session is not None
    result = api.set_repair_config(RepairConfig("high", False, 0.7, 1024).as_dict())
    assert result["accepted"] is True
    assert api._settings_store.load().repair_config == RepairConfig("high", False, 0.7, 1024)
    assert api._manual_processor is None
    assert not cache.exists()
    with pytest.raises(ValueError, match="available"):
        api._adjustments.get("job-1", session.preview_token)


def test_repair_settings_rejected_during_render(tmp_path: Path):
    api = DesktopApi(lambda: IdleProcessor(), job_database=tmp_path / "jobs.sqlite3")
    api._settings_store = SettingsStore(tmp_path / "settings.json")
    api._review_busy = True
    before = api._settings
    result = api.set_repair_config(RepairConfig("high").as_dict())
    assert result["accepted"] is False and api._settings == before
    assert not api._settings_store.path.exists()


def test_invalidation_discards_late_render(tmp_path: Path):
    manager = AdjustmentSessionManager(tmp_path / "cache")
    generation = manager.begin("job-1", "base", [])
    manager.invalidate()
    cache = manager.cache_path(generation, ".png")
    cache.write_bytes(b"late render")
    assert manager.complete(generation, cache, width=1, height=1, elapsed_seconds=0) is None
    assert not cache.exists()


def test_repair_save_failure_keeps_settings_and_preview(tmp_path: Path, monkeypatch):
    api = DesktopApi(lambda: IdleProcessor(), job_database=tmp_path / "jobs.sqlite3")
    api._settings_store = SettingsStore(tmp_path / "settings.json")
    before = api._settings
    generation = api._adjustments.begin("job-1", "base", [])
    cache = api._adjustments.cache_path(generation, ".png")
    cache.write_bytes(b"preview")
    session = api._adjustments.complete(generation, cache, width=1, height=1, elapsed_seconds=0)
    def fail(_):
        raise OSError("disk full")
    monkeypatch.setattr(api._settings_store, "save", fail)
    response = api.set_repair_config(RepairConfig("high").as_dict())
    assert response["accepted"] is False and api._settings == before
    assert session is not None
    assert api._adjustments.get("job-1", session.preview_token).cache_path.exists()


def test_automatic_and_manual_factories_share_saved_repair_config(tmp_path: Path, monkeypatch):
    captures = []
    monkeypatch.setattr(desktop, "build_processor", lambda confidence, margin, config:
                        captures.append(("automatic", config)) or IdleProcessor())
    monkeypatch.setattr(desktop, "build_manual_processor", lambda config:
                        captures.append(("manual", config)) or IdleProcessor())
    api = DesktopApi(lambda: IdleProcessor(), job_database=tmp_path / "jobs.sqlite3")
    api._settings_store = SettingsStore(tmp_path / "settings.json")
    config = RepairConfig("high", False, 0.5, 1024)
    assert api.set_repair_config(config.as_dict())["accepted"]
    api._service._processor_factory()
    api._manual_processor_factory()
    assert captures == [("automatic", config), ("manual", config)]
