"""Tests for schema v6 → v7 migration (projects table + jobs.project_id)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.core.job_store import SCHEMA_VERSION, JobStore
from app.domain.job import JobStatus


def _create_v6_database(database: Path) -> None:
    """Create a minimal v6 database without project_id column or projects table."""
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE schema_info(version INTEGER NOT NULL);
        INSERT INTO schema_info(version) VALUES (6);
        CREATE TABLE jobs (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            output TEXT,
            status TEXT NOT NULL,
            risks_json TEXT NOT NULL DEFAULT '[]',
            error TEXT,
            elapsed_seconds REAL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            file_mtime REAL,
            file_size INTEGER,
            post_processed_output TEXT
        );
        CREATE TABLE detections (
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
        );
        CREATE TABLE mask_revisions (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            commands_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        INSERT INTO jobs(
            id, source, status, created_at, updated_at,
            file_mtime, file_size, post_processed_output
        ) VALUES (
            'job-v6', 'source.jpg', 'completed', 'now', 'now',
            1.0, 100, 'D:/out/final.jpg'
        );
        """
    )
    connection.commit()
    connection.close()


def test_project_id_column_added(tmp_path: Path) -> None:
    """v6 → v7 migration should add project_id column and projects table."""
    database = tmp_path / "jobs.sqlite3"
    _create_v6_database(database)

    with JobStore(database):
        pass

    connection = sqlite3.connect(database)
    assert (
        connection.execute("SELECT version FROM schema_info").fetchone()
        == (SCHEMA_VERSION,)
    )
    job_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(jobs)")
    }
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    indexes = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'"
        ).fetchall()
    }
    connection.close()

    assert "project_id" in job_columns
    assert "projects" in tables
    assert "idx_jobs_project_id" in indexes


def test_create_job_with_project_id(tmp_path: Path) -> None:
    """create_job should accept and persist the project_id parameter."""
    database = tmp_path / "jobs.sqlite3"
    with JobStore(database) as store:
        identifier = store.create_job(
            tmp_path / "source.jpg",
            project_id="proj-abc123",
        )
        job = store.get_job(identifier)

    assert job.project_id == "proj-abc123"

    # Also verify via list_jobs
    with JobStore(database) as store:
        jobs = store.list_jobs()
        assert len(jobs) == 1
        assert jobs[0].project_id == "proj-abc123"


def test_old_jobs_without_project_id_return_none(tmp_path: Path) -> None:
    """Jobs created under v6 should have project_id=None after migration."""
    database = tmp_path / "jobs.sqlite3"
    _create_v6_database(database)

    with JobStore(database) as store:
        job = store.get_job("job-v6")
        assert job.status is JobStatus.COMPLETED
        assert job.post_processed_output == "D:/out/final.jpg"
        # Old job should have no project_id after migration
        assert job.project_id is None

    # Also verify via list_jobs
    with JobStore(database) as store:
        jobs = store.list_jobs()
        assert len(jobs) == 1
        assert jobs[0].project_id is None
