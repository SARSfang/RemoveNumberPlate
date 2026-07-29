"""Small, validated JSON settings store."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from math import isfinite
from pathlib import Path

from app.config import PRESETS, AppPaths
from app.core.exif_writer import ExifConfig
from app.core.mask_builder import (
    DEFAULT_MARGIN_RATIO,
    MAXIMUM_MARGIN_RATIO,
    MINIMUM_MARGIN_RATIO,
)
from app.core.watermark import WatermarkConfig

DEFAULT_PRESET = "balanced"


@dataclass(frozen=True, slots=True)
class PostProcessConfig:
    """Optional post-processing pipeline (rename / watermark / EXIF).

    `naming_template` is empty by default; the renderer falls back to
    `{original}_clean{ext}` when it is empty or whitespace-only.
    """

    enabled: bool = False
    naming_template: str = ""
    watermark: WatermarkConfig = field(default_factory=WatermarkConfig)
    exif: ExifConfig = field(default_factory=ExifConfig)


@dataclass(frozen=True, slots=True)
class WatchFolder:
    """A user-registered watch folder entry.

    `path` is an absolute filesystem path string. `added_at` is an ISO 8601 UTC
    timestamp string used for stable ordering in the settings UI.
    """

    path: str
    enabled: bool
    added_at: str

    def __post_init__(self) -> None:
        if not isinstance(self.path, str) or not self.path.strip():
            raise ValueError("watch folder path must be a non-empty string")
        if not isinstance(self.enabled, bool):
            raise ValueError("watch folder enabled must be a boolean")
        if not isinstance(self.added_at, str) or not self.added_at.strip():
            raise ValueError("watch folder added_at must be a non-empty string")


@dataclass(frozen=True, slots=True)
class UserSettings:
    preset: str = DEFAULT_PRESET
    mask_margin_ratio: float = DEFAULT_MARGIN_RATIO
    watch_folders: tuple[WatchFolder, ...] = ()
    post_process_config: PostProcessConfig = field(default_factory=PostProcessConfig)
    current_project_id: str | None = None

    def __post_init__(self) -> None:
        if self.preset not in PRESETS:
            raise ValueError(f"unknown processing preset: {self.preset}")
        if (
            isinstance(self.mask_margin_ratio, bool)
            or not isinstance(self.mask_margin_ratio, (int, float))
            or not isfinite(self.mask_margin_ratio)
            or not MINIMUM_MARGIN_RATIO
            <= self.mask_margin_ratio
            <= MAXIMUM_MARGIN_RATIO
        ):
            raise ValueError(
                f"mask margin must be between {MINIMUM_MARGIN_RATIO} "
                f"and {MAXIMUM_MARGIN_RATIO}"
            )
        if not isinstance(self.watch_folders, tuple):
            raise ValueError("watch_folders must be a tuple")
        for item in self.watch_folders:
            if not isinstance(item, WatchFolder):
                raise ValueError("watch_folders entries must be WatchFolder instances")
        if not isinstance(self.post_process_config, PostProcessConfig):
            raise ValueError("post_process_config must be a PostProcessConfig instance")
        if self.current_project_id is not None and not isinstance(
            self.current_project_id, str
        ):
            raise ValueError("current_project_id must be a string or None")


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (AppPaths.default().data_dir / "settings.json")

    def load(self) -> UserSettings:
        return self.load_with_recovery()[0]

    def load_with_recovery(self) -> tuple[UserSettings, str | None]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return (
                UserSettings(
                    preset=str(value.get("preset", DEFAULT_PRESET)),
                    mask_margin_ratio=value.get(
                        "mask_margin_ratio",
                        DEFAULT_MARGIN_RATIO,
                    ),
                    watch_folders=_parse_watch_folders(value.get("watch_folders")),
                    post_process_config=_parse_post_process_config(
                        value.get("post_process_config")
                    ),
                    current_project_id=_parse_current_project_id(
                        value.get("current_project_id")
                    ),
                ),
                None,
            )
        except FileNotFoundError:
            return UserSettings(), None
        except OSError:
            return UserSettings(), None
        except (json.JSONDecodeError, ValueError, AttributeError):
            marker = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
            backup = self.path.with_name(f"{self.path.name}.invalid-{marker}")
            try:
                self.path.replace(backup)
            except OSError:
                return UserSettings(), None
            return UserSettings(), backup.name

    def save(self, settings: UserSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {
                    "preset": settings.preset,
                    "mask_margin_ratio": settings.mask_margin_ratio,
                    "watch_folders": [
                        {
                            "path": w.path,
                            "enabled": w.enabled,
                            "added_at": w.added_at,
                        }
                        for w in settings.watch_folders
                    ],
                    "post_process_config": _post_process_config_to_dict(
                        settings.post_process_config
                    ),
                    "current_project_id": settings.current_project_id,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        temporary.replace(self.path)


def _parse_watch_folders(
    raw: object,
) -> tuple[WatchFolder, ...]:
    """Parse watch_folders from JSON. Returns empty tuple on missing/invalid.

    - `null` / missing key → empty tuple (legacy settings compatibility)
    - Non-list value → ValueError (treated as invalid settings, triggers backup)
    - Individual entries that are not dicts or missing required fields →
      ValueError (fail-fast keeps the persisted shape honest)
    """

    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError("watch_folders must be a list")
    parsed: list[WatchFolder] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"watch_folders[{index}] must be an object")
        path_value = item.get("path")
        added_at_value = item.get("added_at")
        if not isinstance(path_value, str) or not path_value.strip():
            raise ValueError(f"watch_folders[{index}].path is required")
        if not isinstance(added_at_value, str) or not added_at_value.strip():
            raise ValueError(f"watch_folders[{index}].added_at is required")
        enabled = item.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError(f"watch_folders[{index}].enabled must be a boolean")
        parsed.append(
            WatchFolder(path=path_value, enabled=enabled, added_at=added_at_value)
        )
    return tuple(parsed)


def _parse_post_process_config(raw: object) -> PostProcessConfig:
    """Parse post_process_config from JSON. Defaults to fully disabled when missing.

    - `null` / missing key → PostProcessConfig() (all disabled, legacy compat)
    - Non-dict value → ValueError (treated as invalid settings, triggers backup)
    - Missing sub-fields default to their WatermarkConfig / ExifConfig defaults
    """

    if raw is None:
        return PostProcessConfig()
    if not isinstance(raw, dict):
        raise ValueError("post_process_config must be an object")

    wm_raw = raw.get("watermark", {})
    if wm_raw is None:
        wm_raw = {}
    if not isinstance(wm_raw, dict):
        raise ValueError("watermark config must be an object")
    watermark = WatermarkConfig(
        enabled=bool(wm_raw.get("enabled", False)),
        type=str(wm_raw.get("type", "text")),
        text=str(wm_raw.get("text", "")),
        font_size=int(wm_raw.get("font_size", 24)),
        color=str(wm_raw.get("color", "#FFFFFF")),
        opacity=float(wm_raw.get("opacity", 0.7)),
        position=str(wm_raw.get("position", "bottom-right")),
        margin=int(wm_raw.get("margin", 16)),
        image_path=str(wm_raw.get("image_path", "")),
        image_scale=float(wm_raw.get("image_scale", 0.2)),
    )

    ex_raw = raw.get("exif", {})
    if ex_raw is None:
        ex_raw = {}
    if not isinstance(ex_raw, dict):
        raise ValueError("exif config must be an object")
    exif = ExifConfig(
        enabled=bool(ex_raw.get("enabled", False)),
        artist=str(ex_raw.get("artist", "")),
        copyright=str(ex_raw.get("copyright", "")),
        description=str(ex_raw.get("description", "")),
    )

    return PostProcessConfig(
        enabled=bool(raw.get("enabled", False)),
        naming_template=str(raw.get("naming_template", "")),
        watermark=watermark,
        exif=exif,
    )


def _post_process_config_to_dict(config: PostProcessConfig) -> dict[str, object]:
    """Serialize PostProcessConfig back to a JSON-friendly dict."""

    return {
        "enabled": config.enabled,
        "naming_template": config.naming_template,
        "watermark": {
            "enabled": config.watermark.enabled,
            "type": config.watermark.type,
            "text": config.watermark.text,
            "font_size": config.watermark.font_size,
            "color": config.watermark.color,
            "opacity": config.watermark.opacity,
            "position": config.watermark.position,
            "margin": config.watermark.margin,
            "image_path": config.watermark.image_path,
            "image_scale": config.watermark.image_scale,
        },
        "exif": {
            "enabled": config.exif.enabled,
            "artist": config.exif.artist,
            "copyright": config.exif.copyright,
            "description": config.exif.description,
        },
    }


def _parse_current_project_id(raw: object) -> str | None:
    """Parse current_project_id from JSON. Returns None when missing or null.

    - `null` / missing key → None (legacy settings compatibility)
    - Non-string value → ValueError (treated as invalid settings, triggers backup)
    """

    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ValueError("current_project_id must be a string or null")
    return raw
