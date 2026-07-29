from pathlib import Path

import pytest

from app.settings import SettingsStore, UserSettings, WatchFolder


def test_settings_round_trip(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.json")

    store.save(UserSettings(preset="quality", mask_margin_ratio=0.72))

    assert store.load() == UserSettings(preset="quality", mask_margin_ratio=0.72)


def test_legacy_settings_receive_new_margin_default(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text('{"preset":"speed"}', encoding="utf-8")

    assert SettingsStore(path).load() == UserSettings(
        preset="speed",
        mask_margin_ratio=0.35,
    )


def test_invalid_settings_fall_back_to_balanced(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    invalid = '{"preset":"unknown"}'
    path.write_text(invalid, encoding="utf-8")

    assert SettingsStore(path).load() == UserSettings()
    assert not path.exists()
    backups = list(tmp_path.glob("settings.json.invalid-*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == invalid


def test_out_of_range_margin_is_recovered(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        '{"preset":"balanced","mask_margin_ratio":1.01}',
        encoding="utf-8",
    )

    assert SettingsStore(path).load() == UserSettings()
    assert not path.exists()


def test_legacy_settings_without_watch_folders_default_to_empty(
    tmp_path: Path,
) -> None:
    """旧 settings.json 没有 watch_folders 字段 → 默认空 tuple。"""
    path = tmp_path / "settings.json"
    path.write_text('{"preset":"speed"}', encoding="utf-8")

    settings = SettingsStore(path).load()

    assert settings.watch_folders == ()


def test_settings_round_trips_watch_folders(tmp_path: Path) -> None:
    """watch_folders 完整 round-trip：保存后读回应相等。"""
    store = SettingsStore(tmp_path / "settings.json")
    original = UserSettings(
        preset="balanced",
        watch_folders=(
            WatchFolder(
                path="D:/商拍/2026-07-客户A",
                enabled=True,
                added_at="2026-07-29T10:30:00Z",
            ),
            WatchFolder(
                path="E:/摄影/婚车跟拍",
                enabled=False,
                added_at="2026-07-29T11:00:00Z",
            ),
        ),
    )

    store.save(original)

    assert store.load() == original


def test_settings_watch_folders_enabled_defaults_to_true(tmp_path: Path) -> None:
    """缺失 enabled 字段时默认 True（向前兼容手动编辑的 JSON）。"""
    path = tmp_path / "settings.json"
    path.write_text(
        '{"preset":"balanced","watch_folders":['
        '{"path":"D:/shoot","added_at":"2026-07-29T10:30:00Z"}'
        "]}",
        encoding="utf-8",
    )

    settings = SettingsStore(path).load()

    assert settings.watch_folders == (
        WatchFolder(
            path="D:/shoot",
            enabled=True,
            added_at="2026-07-29T10:30:00Z",
        ),
    )


def test_settings_watch_folders_missing_path_is_recovered(tmp_path: Path) -> None:
    """watch_folders 项缺 path → 触发 invalid 恢复并备份。"""
    path = tmp_path / "settings.json"
    invalid = (
        '{"preset":"balanced","watch_folders":['
        '{"added_at":"2026-07-29T10:30:00Z"}'
        "]}"
    )
    path.write_text(invalid, encoding="utf-8")

    settings = SettingsStore(path).load()

    assert settings == UserSettings()
    assert not path.exists()
    backups = list(tmp_path.glob("settings.json.invalid-*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == invalid


def test_settings_watch_folders_non_list_value_is_recovered(
    tmp_path: Path,
) -> None:
    """watch_folders 不是 list → 触发 invalid 恢复。"""
    path = tmp_path / "settings.json"
    path.write_text(
        '{"preset":"balanced","watch_folders":"D:/oops"}',
        encoding="utf-8",
    )

    settings = SettingsStore(path).load()

    assert settings == UserSettings()
    assert not path.exists()


def test_watch_folder_rejects_empty_path() -> None:
    with pytest.raises(ValueError):
        WatchFolder(path="   ", enabled=True, added_at="2026-07-29T10:30:00Z")


def test_watch_folder_rejects_empty_added_at() -> None:
    with pytest.raises(ValueError):
        WatchFolder(path="D:/shoot", enabled=True, added_at="   ")
