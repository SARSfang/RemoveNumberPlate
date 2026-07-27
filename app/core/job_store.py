"""SQLite persistence for resumable batch jobs."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.domain.job import JobStatus, RiskReason
from app.domain.result import ProcessingResult

SCHEMA_VERSION = 1
INTERRUPTED_STATUSES = (
    JobStatus.DETECTING,
    JobStatus.INPAINTING,
    JobStatus.WRITING,
)


@dataclass(frozen=True, slots=True)
class StoredJob:
    id: str
    source: Path
    output: Path | None
    status: JobStatus
    risks: tuple[RiskReason, ...]
    error: str | None


class JobStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._initialize()

    def _initialize(self) -> None:
        with self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_info (
                    version INTEGER NOT NULL
                )
                """
            )
            row = self._connection.execute(
                "SELECT version FROM schema_info LIMIT 1"
            ).fetchone()
            if row is None:
                self._connection.execute(
                    "INSERT INTO schema_info(version) VALUES (?)",
                    (SCHEMA_VERSION,),
                )
            elif int(row["version"]) != SCHEMA_VERSION:
                raise RuntimeError(f"unsupported job database version: {row['version']}")
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    output TEXT,
                    status TEXT NOT NULL,
                    risks_json TEXT NOT NULL DEFAULT '[]',
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> JobStore:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def create_job(self, source: Path) -> str:
        identifier = str(uuid4())
        timestamp = datetime.now(UTC).isoformat()
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO jobs(id, source, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (identifier, str(source.resolve()), JobStatus.QUEUED.value, timestamp, timestamp),
            )
        return identifier

    def set_status(self, identifier: str, status: JobStatus) -> None:
        with self._connection:
            cursor = self._connection.execute(
                "UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?",
                (status.value, datetime.now(UTC).isoformat(), identifier),
            )
        if cursor.rowcount != 1:
            raise KeyError(identifier)

    def record_result(self, identifier: str, result: ProcessingResult) -> None:
        with self._connection:
            cursor = self._connection.execute(
                """
                UPDATE jobs
                SET output = ?, status = ?, risks_json = ?, error = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    str(result.output) if result.output else None,
                    result.status.value,
                    json.dumps([risk.value for risk in result.risks]),
                    result.error,
                    datetime.now(UTC).isoformat(),
                    identifier,
                ),
            )
        if cursor.rowcount != 1:
            raise KeyError(identifier)

    def recover_interrupted(self) -> int:
        placeholders = ",".join("?" for _ in INTERRUPTED_STATUSES)
        with self._connection:
            cursor = self._connection.execute(
                f"""
                UPDATE jobs SET status = ?, updated_at = ?
                WHERE status IN ({placeholders})
                """,
                (
                    JobStatus.QUEUED.value,
                    datetime.now(UTC).isoformat(),
                    *(status.value for status in INTERRUPTED_STATUSES),
                ),
            )
        return cursor.rowcount

    def list_jobs(
        self,
        statuses: tuple[JobStatus, ...] | None = None,
        *,
        limit: int = 1000,
    ) -> tuple[StoredJob, ...]:
        parameters: list[object] = []
        where = ""
        if statuses:
            placeholders = ",".join("?" for _ in statuses)
            where = f"WHERE status IN ({placeholders})"
            parameters.extend(status.value for status in statuses)
        parameters.append(limit)
        rows = self._connection.execute(
            f"""
            SELECT id, source, output, status, risks_json, error
            FROM jobs {where}
            ORDER BY created_at ASC
            LIMIT ?
            """,
            parameters,
        ).fetchall()
        return tuple(
            StoredJob(
                id=str(row["id"]),
                source=Path(str(row["source"])),
                output=Path(str(row["output"])) if row["output"] else None,
                status=JobStatus(str(row["status"])),
                risks=tuple(
                    RiskReason(value) for value in json.loads(str(row["risks_json"]))
                ),
                error=str(row["error"]) if row["error"] else None,
            )
            for row in rows
        )

    def counts(self) -> dict[str, int]:
        rows = self._connection.execute(
            "SELECT status, COUNT(*) AS count FROM jobs GROUP BY status"
        ).fetchall()
        return {str(row["status"]): int(row["count"]) for row in rows}
