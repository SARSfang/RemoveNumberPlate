"""Project store: per-client preset persistence in the jobs database."""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.settings import (
    PostProcessConfig,
    _parse_post_process_config,
    _post_process_config_to_dict,
)

_VALID_OUTPUT_MODES = frozenset(
    {"beside_source", "project_subfolder", "fixed_directory"}
)


@dataclass(frozen=True, slots=True)
class OutputDirectoryRule:
    """Where post-processed outputs land."""

    mode: str = "beside_source"  # "beside_source" | "project_subfolder" | "fixed_directory"
    subfolder_name: str = ""  # for project_subfolder mode
    fixed_directory: str = ""  # for fixed_directory mode

    def __post_init__(self) -> None:
        if self.mode not in _VALID_OUTPUT_MODES:
            raise ValueError(f"unknown output directory mode: {self.mode}")
        if self.mode == "fixed_directory" and not self.fixed_directory.strip():
            raise ValueError("fixed_directory mode requires fixed_directory")


@dataclass(frozen=True, slots=True)
class ProjectPreset:
    """A saved client/project preset."""

    id: str  # UUID
    name: str
    preset: str = "balanced"  # processing preset
    mask_margin_ratio: float = 0.08
    post_process_config: PostProcessConfig = field(default_factory=PostProcessConfig)
    output_directory_rule: OutputDirectoryRule = field(default_factory=OutputDirectoryRule)
    created_at: str = ""
    last_used_at: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("project name must not be empty")
        if not self.id.strip():
            raise ValueError("project id must not be empty")


def _output_directory_rule_to_dict(rule: OutputDirectoryRule) -> dict[str, object]:
    return {
        "mode": rule.mode,
        "subfolder_name": rule.subfolder_name,
        "fixed_directory": rule.fixed_directory,
    }


def _parse_output_directory_rule(raw: object) -> OutputDirectoryRule:
    if raw is None:
        return OutputDirectoryRule()
    if not isinstance(raw, dict):
        raise ValueError("output_directory_rule must be an object")
    return OutputDirectoryRule(
        mode=str(raw.get("mode", "beside_source")),
        subfolder_name=str(raw.get("subfolder_name", "")),
        fixed_directory=str(raw.get("fixed_directory", "")),
    )


def _preset_payload_to_dict(preset: ProjectPreset) -> dict[str, object]:
    """Serialize the mutable preset fields (excludes id/name/timestamps)."""
    return {
        "preset": preset.preset,
        "mask_margin_ratio": preset.mask_margin_ratio,
        "post_process_config": _post_process_config_to_dict(preset.post_process_config),
        "output_directory_rule": _output_directory_rule_to_dict(
            preset.output_directory_rule
        ),
    }


def _row_to_project(row: sqlite3.Row) -> ProjectPreset:
    """Build a ProjectPreset from a database row."""
    payload = json.loads(str(row["preset_json"]))
    if not isinstance(payload, dict):
        raise ValueError("preset_json must be an object")
    return ProjectPreset(
        id=str(row["id"]),
        name=str(row["name"]),
        preset=str(payload.get("preset", "balanced")),
        mask_margin_ratio=float(payload.get("mask_margin_ratio", 0.08)),
        post_process_config=_parse_post_process_config(
            payload.get("post_process_config")
        ),
        output_directory_rule=_parse_output_directory_rule(
            payload.get("output_directory_rule")
        ),
        created_at=str(row["created_at"]),
        last_used_at=(
            str(row["last_used_at"]) if row["last_used_at"] is not None else ""
        ),
    )


class ProjectStore:
    """CRUD for projects in the jobs database."""

    def __init__(self, database_path: Path) -> None:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._database = database_path
        self._connection = sqlite3.connect(database_path)
        try:
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA journal_mode=WAL")
        except Exception:
            self._connection.close()
            raise

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> ProjectStore:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def list_projects(self) -> list[ProjectPreset]:
        """List all projects, ordered by last_used_at DESC, name ASC."""
        rows = self._connection.execute(
            """
            SELECT id, name, preset_json, created_at, last_used_at
            FROM projects
            ORDER BY last_used_at DESC, name ASC
            """
        ).fetchall()
        return [_row_to_project(row) for row in rows]

    def get_project(self, project_id: str) -> ProjectPreset | None:
        row = self._connection.execute(
            """
            SELECT id, name, preset_json, created_at, last_used_at
            FROM projects WHERE id = ?
            """,
            (project_id,),
        ).fetchone()
        if row is None:
            return None
        return _row_to_project(row)

    def create_project(
        self,
        name: str,
        preset: str = "balanced",
        mask_margin_ratio: float = 0.08,
        post_process_config: PostProcessConfig | None = None,
        output_directory_rule: OutputDirectoryRule | None = None,
    ) -> ProjectPreset:
        project_id = uuid.uuid4().hex
        timestamp = datetime.now(UTC).isoformat()
        project = ProjectPreset(
            id=project_id,
            name=name,
            preset=preset,
            mask_margin_ratio=mask_margin_ratio,
            post_process_config=post_process_config or PostProcessConfig(),
            output_directory_rule=output_directory_rule or OutputDirectoryRule(),
            created_at=timestamp,
            last_used_at="",
        )
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO projects(id, name, preset_json, created_at, last_used_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    project.id,
                    project.name,
                    json.dumps(_preset_payload_to_dict(project), ensure_ascii=False),
                    project.created_at,
                    project.last_used_at,
                ),
            )
        return project

    def update_project(self, project_id: str, **kwargs: Any) -> ProjectPreset:
        """Update project fields. Raises KeyError if not found."""
        current = self.get_project(project_id)
        if current is None:
            raise KeyError(project_id)
        allowed_keys = {
            "name",
            "preset",
            "mask_margin_ratio",
            "post_process_config",
            "output_directory_rule",
        }
        for key in kwargs:
            if key not in allowed_keys:
                raise ValueError(f"unknown project field: {key}")
        updated = replace(current, **kwargs)
        with self._connection:
            cursor = self._connection.execute(
                """
                UPDATE projects
                SET name = ?, preset_json = ?
                WHERE id = ?
                """,
                (
                    updated.name,
                    json.dumps(_preset_payload_to_dict(updated), ensure_ascii=False),
                    project_id,
                ),
            )
        if cursor.rowcount != 1:
            raise KeyError(project_id)
        return updated

    def delete_project(self, project_id: str) -> bool:
        """Delete project. Returns True if deleted."""
        with self._connection:
            cursor = self._connection.execute(
                "DELETE FROM projects WHERE id = ?",
                (project_id,),
            )
        return cursor.rowcount == 1

    def touch_last_used(self, project_id: str) -> None:
        """Update last_used_at to now."""
        timestamp = datetime.now(UTC).isoformat()
        with self._connection:
            cursor = self._connection.execute(
                "UPDATE projects SET last_used_at = ? WHERE id = ?",
                (timestamp, project_id),
            )
        if cursor.rowcount != 1:
            raise KeyError(project_id)
