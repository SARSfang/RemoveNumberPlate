import sqlite3
from pathlib import Path

from app.core.job_store import JobStore, prepare_job_database
from app.domain.detection import Detection, Quadrilateral
from app.domain.job import JobStatus, RiskReason
from app.domain.result import ProcessingResult


def test_job_store_records_result_and_counts(tmp_path: Path) -> None:
    source = tmp_path / "source.jpg"
    polygon = Quadrilateral(((10, 20), (100, 18), (98, 50), (12, 52)))
    detection = Detection(polygon.bounding_box, 0.55, polygon=polygon)
    with JobStore(tmp_path / "jobs.sqlite3") as store:
        identifier = store.create_job(source)
        store.set_status(identifier, JobStatus.DETECTING)
        store.record_result(
            identifier,
            ProcessingResult(
                None,
                1,
                risks=(RiskReason.LOW_CONFIDENCE,),
                status=JobStatus.REVIEW_REQUIRED,
                detection_count=1,
                detections=(detection,),
            ),
        )

        jobs = store.list_jobs()

        assert jobs[0].status is JobStatus.REVIEW_REQUIRED
        assert jobs[0].risks == (RiskReason.LOW_CONFIDENCE,)
        assert jobs[0].detections == (detection,)
        assert jobs[0].elapsed_seconds == 1
        assert jobs[0].created_at
        assert jobs[0].updated_at
        assert store.counts() == {"review_required": 1}


def test_job_store_recovers_interrupted_state(tmp_path: Path) -> None:
    with JobStore(tmp_path / "jobs.sqlite3") as store:
        identifier = store.create_job(tmp_path / "source.jpg")
        store.set_status(identifier, JobStatus.INPAINTING)

        recovered = store.recover_interrupted()

        assert recovered == 1
        assert store.list_jobs()[0].status is JobStatus.QUEUED


def test_job_store_round_trips_latest_mask_revision(tmp_path: Path) -> None:
    with JobStore(tmp_path / "jobs.sqlite3") as store:
        identifier = store.create_job(tmp_path / "source.jpg")
        first = [{"type": "rectangle", "start": [1, 2], "end": [3, 4]}]
        second = [{"type": "brush_add", "points": [[5, 6]], "radius": 10}]

        store.record_mask_revision(identifier, first)
        store.record_mask_revision(identifier, second)

        assert store.latest_mask_revision(identifier) == second


def test_job_store_migrates_v1_database_without_losing_jobs(tmp_path: Path) -> None:
    database = tmp_path / "jobs.sqlite3"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE schema_info(version INTEGER NOT NULL)")
    connection.execute("INSERT INTO schema_info(version) VALUES (1)")
    connection.commit()
    connection.close()

    with JobStore(database) as store:
        identifier = store.create_job(tmp_path / "source.jpg")
        assert store.get_job(identifier).status is JobStatus.QUEUED

    connection = sqlite3.connect(database)
    version = connection.execute("SELECT version FROM schema_info").fetchone()
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    connection.close()
    assert version == (4,)
    assert {"jobs", "detections", "mask_revisions"} <= tables


def test_job_store_migrates_v3_detection_to_polygon_fallback(
    tmp_path: Path,
) -> None:
    database = tmp_path / "jobs.sqlite3"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE schema_info(version INTEGER NOT NULL);
        INSERT INTO schema_info(version) VALUES (3);
        CREATE TABLE jobs (
            id TEXT PRIMARY KEY,
            source TEXT NOT NULL,
            output TEXT,
            status TEXT NOT NULL,
            risks_json TEXT NOT NULL DEFAULT '[]',
            error TEXT,
            elapsed_seconds REAL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
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
            PRIMARY KEY(job_id, ordinal)
        );
        CREATE TABLE mask_revisions (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            commands_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        INSERT INTO jobs(
            id, source, status, created_at, updated_at
        ) VALUES ('job-1', 'source.jpg', 'completed', 'now', 'now');
        INSERT INTO detections(
            job_id, ordinal, x1, y1, x2, y2, confidence
        ) VALUES ('job-1', 0, 10, 20, 100, 50, 0.9);
        """
    )
    connection.commit()
    connection.close()

    with JobStore(database) as store:
        job = store.get_job("job-1")
        store.verify_integrity()

    assert job.detections[0].polygon is None
    assert job.detections[0].effective_polygon == Quadrilateral(
        ((10, 20), (100, 20), (100, 50), (10, 50))
    )
    connection = sqlite3.connect(database)
    assert connection.execute("SELECT version FROM schema_info").fetchone() == (4,)
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(detections)")
    }
    connection.close()
    assert "polygon_json" in columns


def test_prepare_job_database_quarantines_confirmed_corruption(
    tmp_path: Path,
) -> None:
    database = tmp_path / "jobs.sqlite3"
    corrupt_payload = b"this is not sqlite"
    database.write_bytes(corrupt_payload)

    backup = prepare_job_database(database)

    assert backup is not None
    assert backup.name.startswith("jobs.sqlite3.corrupt-")
    assert backup.read_bytes() == corrupt_payload
    with JobStore(database) as store:
        store.verify_integrity()
        assert store.counts() == {}


def test_prepare_job_database_does_not_quarantine_future_schema(
    tmp_path: Path,
) -> None:
    database = tmp_path / "jobs.sqlite3"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE schema_info(version INTEGER NOT NULL)")
    connection.execute("INSERT INTO schema_info(version) VALUES (999)")
    connection.commit()
    connection.close()

    try:
        prepare_job_database(database)
    except RuntimeError as error:
        assert "unsupported job database version" in str(error)
    else:
        raise AssertionError("future schema should be rejected")

    assert database.is_file()
    assert not list(tmp_path.glob("*.corrupt-*"))
