from pathlib import Path

from app.core.job_store import JobStore
from app.domain.job import JobStatus, RiskReason
from app.domain.result import ProcessingResult


def test_job_store_records_result_and_counts(tmp_path: Path) -> None:
    source = tmp_path / "source.jpg"
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
            ),
        )

        jobs = store.list_jobs()

        assert jobs[0].status is JobStatus.REVIEW_REQUIRED
        assert jobs[0].risks == (RiskReason.LOW_CONFIDENCE,)
        assert store.counts() == {"review_required": 1}


def test_job_store_recovers_interrupted_state(tmp_path: Path) -> None:
    with JobStore(tmp_path / "jobs.sqlite3") as store:
        identifier = store.create_job(tmp_path / "source.jpg")
        store.set_status(identifier, JobStatus.INPAINTING)

        recovered = store.recover_interrupted()

        assert recovered == 1
        assert store.list_jobs()[0].status is JobStatus.QUEUED
