"""SQLite persistence for resumable batch jobs."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.domain.detection import BoundingBox, Detection, Quadrilateral
from app.domain.job import JobStatus, RiskReason
from app.domain.result import ProcessingResult

SCHEMA_VERSION = 4
INTERRUPTED_STATUSES = (
    JobStatus.DETECTING,
    JobStatus.INPAINTING,
    JobStatus.WRITING,
)
CORRUPTION_CODES = frozenset({sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB})


class DatabaseCorruptionError(sqlite3.DatabaseError):
    """SQLite integrity checking proved that the history database is corrupt."""


def _is_confirmed_corruption(error: sqlite3.DatabaseError) -> bool:
    if isinstance(error, DatabaseCorruptionError):
        return True
    return getattr(error, "sqlite_errorcode", None) in CORRUPTION_CODES


def _quarantine_database(path: Path) -> Path:
    marker = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    backup = path.with_name(f"{path.name}.corrupt-{marker}")
    path.replace(backup)
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = path.with_name(path.name + suffix)
        if sidecar.exists():
            sidecar.replace(backup.with_name(backup.name + suffix))
    return backup


def prepare_job_database(path: Path) -> Path | None:
    """Open and verify history, quarantining only proven corruption."""

    try:
        with JobStore(path) as store:
            store.verify_integrity()
        return None
    except sqlite3.DatabaseError as error:
        if not _is_confirmed_corruption(error) or not path.is_file():
            raise
        backup = _quarantine_database(path)
        with JobStore(path) as store:
            store.verify_integrity()
        return backup


@dataclass(frozen=True, slots=True)
class StoredJob:
    id: str
    source: Path
    output: Path | None
    status: JobStatus
    risks: tuple[RiskReason, ...]
    error: str | None
    detections: tuple[Detection, ...]
    elapsed_seconds: float | None
    created_at: str
    updated_at: str


class JobStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path)
        try:
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA journal_mode=WAL")
            self._initialize()
        except Exception:
            self._connection.close()
            raise

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
            current_version = int(row["version"]) if row is not None else 0
            if current_version > SCHEMA_VERSION:
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
                    elapsed_seconds REAL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS detections (
                    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                    ordinal INTEGER NOT NULL,
                    x1 REAL NOT NULL,
                    y1 REAL NOT NULL,
                    x2 REAL NOT NULL,
                    y2 REAL NOT NULL,
                    confidence REAL NOT NULL,
                    source_tile INTEGER,
                    polygon_json TEXT,
                    PRIMARY KEY(job_id, ordinal)
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS mask_revisions (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                    commands_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            if row is None:
                self._connection.execute(
                    "INSERT INTO schema_info(version) VALUES (?)",
                    (SCHEMA_VERSION,),
                )
            elif current_version < SCHEMA_VERSION:
                if current_version < 3:
                    columns = {
                        str(column["name"])
                        for column in self._connection.execute("PRAGMA table_info(jobs)")
                    }
                    if "elapsed_seconds" not in columns:
                        self._connection.execute(
                            "ALTER TABLE jobs ADD COLUMN elapsed_seconds REAL"
                        )
                if current_version < 4:
                    detection_columns = {
                        str(column["name"])
                        for column in self._connection.execute(
                            "PRAGMA table_info(detections)"
                        )
                    }
                    if "polygon_json" not in detection_columns:
                        self._connection.execute(
                            "ALTER TABLE detections ADD COLUMN polygon_json TEXT"
                        )
                self._connection.execute(
                    "UPDATE schema_info SET version = ?",
                    (SCHEMA_VERSION,),
                )

    def close(self) -> None:
        self._connection.close()

    def verify_integrity(self) -> None:
        row = self._connection.execute("PRAGMA quick_check").fetchone()
        if row is None or str(row[0]).lower() != "ok":
            detail = str(row[0]) if row is not None else "no result"
            raise DatabaseCorruptionError(f"SQLite quick_check failed: {detail}")

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
                    , elapsed_seconds = ?
                WHERE id = ?
                """,
                (
                    str(result.output) if result.output else None,
                    result.status.value,
                    json.dumps([risk.value for risk in result.risks]),
                    result.error,
                    datetime.now(UTC).isoformat(),
                    result.elapsed_seconds,
                    identifier,
                ),
            )
            self._connection.execute(
                "DELETE FROM detections WHERE job_id = ?",
                (identifier,),
            )
            self._connection.executemany(
                """
                INSERT INTO detections(
                    job_id, ordinal, x1, y1, x2, y2, confidence, source_tile,
                    polygon_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    (
                        identifier,
                        ordinal,
                        detection.box.x1,
                        detection.box.y1,
                        detection.box.x2,
                        detection.box.y2,
                        detection.confidence,
                        detection.source_tile,
                        (
                            json.dumps(detection.polygon.points)
                            if detection.polygon is not None
                            else None
                        ),
                    )
                    for ordinal, detection in enumerate(result.detections)
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
            SELECT id, source, output, status, risks_json, error,
                   elapsed_seconds, created_at, updated_at
            FROM jobs {where}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            parameters,
        ).fetchall()
        return tuple(self._stored_job_from_row(row) for row in rows)

    def get_job(self, identifier: str) -> StoredJob:
        row = self._connection.execute(
            """
            SELECT id, source, output, status, risks_json, error,
                   elapsed_seconds, created_at, updated_at
            FROM jobs WHERE id = ?
            """,
            (identifier,),
        ).fetchone()
        if row is None:
            raise KeyError(identifier)
        return self._stored_job_from_row(row)

    def _stored_job_from_row(self, row: sqlite3.Row) -> StoredJob:
        identifier = str(row["id"])
        detection_rows = self._connection.execute(
            """
            SELECT x1, y1, x2, y2, confidence, source_tile, polygon_json
            FROM detections WHERE job_id = ? ORDER BY ordinal ASC
            """,
            (identifier,),
        ).fetchall()
        detections: list[Detection] = []
        for detection in detection_rows:
            polygon: Quadrilateral | None = None
            if detection["polygon_json"] is not None:
                try:
                    raw_polygon = json.loads(str(detection["polygon_json"]))
                    polygon = Quadrilateral(
                        tuple((float(point[0]), float(point[1])) for point in raw_polygon)
                    )
                except (TypeError, ValueError, IndexError, json.JSONDecodeError) as error:
                    raise RuntimeError("invalid persisted detection polygon") from error
            detections.append(
                Detection(
                    BoundingBox(
                        float(detection["x1"]),
                        float(detection["y1"]),
                        float(detection["x2"]),
                        float(detection["y2"]),
                    ),
                    float(detection["confidence"]),
                    int(detection["source_tile"])
                    if detection["source_tile"] is not None
                    else None,
                    polygon,
                )
            )
        return StoredJob(
            id=identifier,
            source=Path(str(row["source"])),
            output=Path(str(row["output"])) if row["output"] else None,
            status=JobStatus(str(row["status"])),
            risks=tuple(
                RiskReason(value) for value in json.loads(str(row["risks_json"]))
            ),
            error=str(row["error"]) if row["error"] else None,
            detections=tuple(detections),
            elapsed_seconds=(
                float(row["elapsed_seconds"])
                if row["elapsed_seconds"] is not None
                else None
            ),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def record_mask_revision(
        self,
        identifier: str,
        commands: Sequence[Mapping[str, object]],
    ) -> str:
        self.get_job(identifier)
        revision_id = str(uuid4())
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO mask_revisions(id, job_id, commands_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    revision_id,
                    identifier,
                    json.dumps(list(commands), ensure_ascii=False),
                    datetime.now(UTC).isoformat(),
                ),
            )
        return revision_id

    def latest_mask_revision(self, identifier: str) -> list[dict[str, object]]:
        row = self._connection.execute(
            """
            SELECT commands_json FROM mask_revisions
            WHERE job_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1
            """,
            (identifier,),
        ).fetchone()
        if row is None:
            return []
        value = json.loads(str(row["commands_json"]))
        if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
            raise RuntimeError("invalid persisted mask revision")
        return value

    def counts(self) -> dict[str, int]:
        rows = self._connection.execute(
            "SELECT status, COUNT(*) AS count FROM jobs GROUP BY status"
        ).fetchall()
        return {str(row["status"]): int(row["count"]) for row in rows}
