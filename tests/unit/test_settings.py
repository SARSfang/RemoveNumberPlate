from pathlib import Path

from app.settings import SettingsStore, UserSettings


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
