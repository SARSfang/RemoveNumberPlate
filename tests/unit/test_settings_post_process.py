"""Unit tests for PostProcessConfig in settings."""

from __future__ import annotations

import json
from pathlib import Path

from app.core.exif_writer import ExifConfig
from app.core.watermark import WatermarkConfig
from app.settings import (
    PostProcessConfig,
    SettingsStore,
    UserSettings,
)


def test_default_post_process_config_disabled() -> None:
    """默认 PostProcessConfig 应全部禁用、模板为空。"""
    config = PostProcessConfig()

    assert config.enabled is False
    assert config.naming_template == ""
    assert config.watermark == WatermarkConfig()
    assert config.exif == ExifConfig()
    assert config.watermark.enabled is False
    assert config.exif.enabled is False


def test_parse_post_process_config_full(tmp_path: Path) -> None:
    """完整 post_process_config JSON 应正确解析。"""
    path = tmp_path / "settings.json"
    payload = {
        "preset": "balanced",
        "post_process_config": {
            "enabled": True,
            "naming_template": "{client}_{seq:03}{ext}",
            "watermark": {
                "enabled": True,
                "text": "© acme",
                "font_size": 32,
                "color": "#FFAA00",
                "opacity": 0.5,
                "position": "top-left",
                "margin": 8,
            },
            "exif": {
                "enabled": True,
                "artist": "photographer",
                "copyright": "© 2026",
                "description": "batch post-process",
            },
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    settings = SettingsStore(path).load()

    assert settings.post_process_config.enabled is True
    assert settings.post_process_config.naming_template == "{client}_{seq:03}{ext}"
    assert settings.post_process_config.watermark == WatermarkConfig(
        enabled=True,
        text="© acme",
        font_size=32,
        color="#FFAA00",
        opacity=0.5,
        position="top-left",
        margin=8,
    )
    assert settings.post_process_config.exif == ExifConfig(
        enabled=True,
        artist="photographer",
        copyright="© 2026",
        description="batch post-process",
    )


def test_parse_post_process_config_missing_fields_defaults(
    tmp_path: Path,
) -> None:
    """缺失子字段时回退到 WatermarkConfig / ExifConfig 默认值。"""
    path = tmp_path / "settings.json"
    payload = {
        "preset": "balanced",
        "post_process_config": {
            "enabled": True,
            "naming_template": "{original}_clean{ext}",
            "watermark": {"enabled": True},
            "exif": {"enabled": True},
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    settings = SettingsStore(path).load()

    assert settings.post_process_config.enabled is True
    assert settings.post_process_config.watermark.enabled is True
    # 缺失字段应回退到 WatermarkConfig 默认值
    assert settings.post_process_config.watermark.text == ""
    assert settings.post_process_config.watermark.font_size == 24
    assert settings.post_process_config.watermark.color == "#FFFFFF"
    assert settings.post_process_config.watermark.opacity == 0.7
    assert settings.post_process_config.watermark.position == "bottom-right"
    assert settings.post_process_config.watermark.margin == 16
    assert settings.post_process_config.exif.enabled is True
    assert settings.post_process_config.exif.artist == ""
    assert settings.post_process_config.exif.copyright == ""
    assert settings.post_process_config.exif.description == ""


def test_save_load_round_trip(tmp_path: Path) -> None:
    """完整 round-trip：保存后读回应相等（含 watermark + exif 子配置）。"""
    store = SettingsStore(tmp_path / "settings.json")
    original = UserSettings(
        preset="quality",
        mask_margin_ratio=0.4,
        post_process_config=PostProcessConfig(
            enabled=True,
            naming_template="{client}_{seq:03}{ext}",
            watermark=WatermarkConfig(
                enabled=True,
                text="© acme",
                font_size=32,
                color="#FFAA00",
                opacity=0.5,
                position="top-left",
                margin=8,
            ),
            exif=ExifConfig(
                enabled=True,
                artist="photographer",
                copyright="© 2026",
                description="batch post-process",
            ),
        ),
    )

    store.save(original)
    loaded = store.load()

    assert loaded == original


def test_legacy_settings_without_post_process_config_defaults(
    tmp_path: Path,
) -> None:
    """旧 settings.json 没有 post_process_config 字段 → 默认全禁用。"""
    path = tmp_path / "settings.json"
    path.write_text('{"preset":"balanced"}', encoding="utf-8")

    settings = SettingsStore(path).load()

    assert settings.post_process_config == PostProcessConfig()
    assert settings.post_process_config.enabled is False


def test_post_process_config_non_object_is_recovered(
    tmp_path: Path,
) -> None:
    """post_process_config 不是 object → 触发 invalid 恢复并备份。"""
    path = tmp_path / "settings.json"
    invalid = '{"preset":"balanced","post_process_config":"oops"}'
    path.write_text(invalid, encoding="utf-8")

    settings = SettingsStore(path).load()

    assert settings == UserSettings()
    assert not path.exists()
    backups = list(tmp_path.glob("settings.json.invalid-*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == invalid


def test_post_process_config_watermark_non_object_is_recovered(
    tmp_path: Path,
) -> None:
    """post_process_config.watermark 不是 object → 触发 invalid 恢复。"""
    path = tmp_path / "settings.json"
    invalid = (
        '{"preset":"balanced","post_process_config":'
        '{"enabled":true,"watermark":"oops"}}'
    )
    path.write_text(invalid, encoding="utf-8")

    settings = SettingsStore(path).load()

    assert settings == UserSettings()
    assert not path.exists()


def test_parse_watermark_image_type(tmp_path: Path) -> None:
    """图片水印配置字段 (type, image_path, image_scale) 应被正确解析。"""
    path = tmp_path / "settings.json"
    payload = {
        "preset": "balanced",
        "post_process_config": {
            "enabled": True,
            "watermark": {
                "enabled": True,
                "type": "image",
                "image_path": "C:/watermark/logo.png",
                "image_scale": 0.5,
                "opacity": 0.6,
                "position": "center",
            },
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    settings = SettingsStore(path).load()

    watermark = settings.post_process_config.watermark
    assert watermark.type == "image"
    assert watermark.image_path == "C:/watermark/logo.png"
    assert watermark.image_scale == 0.5
    assert watermark.opacity == 0.6
    assert watermark.position == "center"


def test_parse_watermark_missing_fields_default(tmp_path: Path) -> None:
    """缺失 image_* 字段时回退到默认值（type=text, image_path="", image_scale=0.2）。"""
    path = tmp_path / "settings.json"
    payload = {
        "preset": "balanced",
        "post_process_config": {
            "enabled": True,
            "watermark": {"enabled": True, "text": "© acme"},
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    settings = SettingsStore(path).load()

    watermark = settings.post_process_config.watermark
    assert watermark.type == "text"
    assert watermark.image_path == ""
    assert watermark.image_scale == 0.2


def test_save_load_watermark_image_round_trip(tmp_path: Path) -> None:
    """图片水印配置的完整 round-trip 保存/读取。"""
    store = SettingsStore(tmp_path / "settings.json")
    original = UserSettings(
        preset="balanced",
        post_process_config=PostProcessConfig(
            enabled=True,
            watermark=WatermarkConfig(
                enabled=True,
                type="image",
                image_path="/var/logos/watermark.png",
                image_scale=0.35,
                opacity=0.8,
                position="top-right",
                margin=20,
            ),
        ),
    )

    store.save(original)
    loaded = store.load()

    assert loaded == original
    assert loaded.post_process_config.watermark.type == "image"
    assert loaded.post_process_config.watermark.image_path == "/var/logos/watermark.png"
    assert loaded.post_process_config.watermark.image_scale == 0.35
