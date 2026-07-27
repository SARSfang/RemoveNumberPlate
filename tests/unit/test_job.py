from pathlib import Path

import pytest

from app.domain.job import ImageJob, JobStatus


def test_image_job_defaults_to_queued() -> None:
    job = ImageJob(Path("input.jpg"), Path("output.jpg"))

    assert job.status is JobStatus.QUEUED


def test_image_job_never_targets_source() -> None:
    source = Path("input.jpg")

    with pytest.raises(ValueError, match="must not overwrite"):
        ImageJob(source, source)
