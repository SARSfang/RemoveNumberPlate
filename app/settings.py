"""Small, validated JSON settings store."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.config import PRESETS, AppPaths

DEFAULT_PRESET = "balanced"


@dataclass(frozen=True, slots=True)
class UserSettings:
    preset: str = DEFAULT_PRESET

    def __post_init__(self) -> None:
        if self.preset not in PRESETS:
            raise ValueError(f"unknown processing preset: {self.preset}")


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (AppPaths.default().data_dir / "settings.json")

    def load(self) -> UserSettings:
        return self.load_with_recovery()[0]

    def load_with_recovery(self) -> tuple[UserSettings, str | None]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return (
                UserSettings(preset=str(value.get("preset", DEFAULT_PRESET))),
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
            json.dumps({"preset": settings.preset}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.path)
