"""History search: query and filter jobs by status, date, name, project."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.core.job_store import JobStore, StoredJob


@dataclass(frozen=True, slots=True)
class HistoryQuery:
    """Search criteria for history listing."""

    statuses: tuple[str, ...] = ()  # empty = all statuses
    date_from: str | None = None  # YYYY-MM-DD inclusive
    date_to: str | None = None  # YYYY-MM-DD inclusive
    name_contains: str = ""  # case-insensitive substring
    project_ids: tuple[str, ...] = ()  # empty = all projects (including None)
    include_no_project: bool = True  # include jobs without project_id
    limit: int = 500
    offset: int = 0


class HistorySearchService:
    """Query jobs with flexible filtering."""

    def __init__(self, database_path: Path) -> None:
        self._database = database_path

    def search(self, query: HistoryQuery) -> list[StoredJob]:
        """Execute search and return matching jobs."""
        where_clause, params = self._build_where(query)
        sql = (
            "SELECT id, source, output, status, risks_json, error, "
            "elapsed_seconds, created_at, updated_at, file_mtime, file_size, "
            f"post_processed_output, project_id FROM jobs {where_clause} "
            "ORDER BY created_at DESC LIMIT ? OFFSET ?"
        )
        params_with_pagination = [*params, query.limit, query.offset]
        with JobStore(self._database) as store:
            rows = store._connection.execute(sql, params_with_pagination).fetchall()
            return [store._stored_job_from_row(row) for row in rows]

    def count(self, query: HistoryQuery) -> int:
        """Return total count of matching jobs (ignoring limit/offset)."""
        where_clause, params = self._build_where(query)
        sql = f"SELECT COUNT(*) FROM jobs {where_clause}"
        with JobStore(self._database) as store:
            row = store._connection.execute(sql, params).fetchone()
            return int(row[0]) if row is not None else 0

    def _build_where(self, query: HistoryQuery) -> tuple[str, list[str]]:
        """Build WHERE clause and parameters from query criteria."""
        conditions: list[str] = []
        params: list[str] = []

        if query.statuses:
            placeholders = ",".join("?" for _ in query.statuses)
            conditions.append(f"status IN ({placeholders})")
            params.extend(query.statuses)

        if query.date_from is not None:
            conditions.append("created_at >= ?")
            params.append(f"{query.date_from}T00:00:00")

        if query.date_to is not None:
            conditions.append("created_at <= ?")
            params.append(f"{query.date_to}T23:59:59.999999")

        if query.name_contains:
            conditions.append("source LIKE ? COLLATE NOCASE")
            params.append(f"%{query.name_contains}%")

        if query.project_ids:
            placeholders = ",".join("?" for _ in query.project_ids)
            if query.include_no_project:
                conditions.append(
                    f"(project_id IN ({placeholders}) OR project_id IS NULL)"
                )
            else:
                conditions.append(f"project_id IN ({placeholders})")
            params.extend(query.project_ids)
        elif not query.include_no_project:
            conditions.append("project_id IS NOT NULL")

        where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        return where_clause, params
