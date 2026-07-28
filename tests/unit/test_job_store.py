import sqlite3
from pathlib import Path

from app.core.job_store import JobStore, prepare_job_database
from app.domain.detection import BoundingBox, Detection
from app.domain.job import JobStatus, RiskReason
from app.domain.result import ProcessingResult


def test_job_store_records_result_and_counts(tmp_path: Path) -> None:
    source = tmp_path / "source.jpg"
    detection = Detection(BoundingBox(10, 20, 100, 50), 0.55)
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
    assert version == (3,)
    assert {"jobs", "detections", "mask_revisions"} <= tables


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
