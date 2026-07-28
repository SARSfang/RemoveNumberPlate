from __future__ import annotations

from pathlib import Path

from PIL import Image

from app.core.job_preview import (
    MAIN_PREVIEW_BOUNDS,
    THUMBNAIL_BOUNDS,
    JobPreview,
    PreviewKind,
    PreviewUnavailableReason,
    build_job_preview,
)
from app.core.job_store import JobStore
from app.domain.job import JobStatus
from app.domain.result import ProcessingResult


def _stored_job(
    tmp_path: Path,
    source: Path,
    *,
    output: Path | None = None,
):
    database = tmp_path / "jobs.sqlite3"
    with JobStore(database) as store:
        identifier = store.create_job(source)
        if output is not None:
            store.record_result(
                identifier,
                ProcessingResult(output, 0.1, status=JobStatus.COMPLETED),
            )
        return store.get_job(identifier)


def test_original_preview_is_bounded_and_contains_no_path(tmp_path: Path) -> None:
    source = tmp_path / "wide.jpg"
    Image.new("RGB", (3000, 2000), "navy").save(source)
    job = _stored_job(tmp_path, source)

    result = build_job_preview(job, PreviewKind.ORIGINAL)

    assert result.available
    assert (result.preview_width, result.preview_height) == MAIN_PREVIEW_BOUNDS
    assert (result.width, result.height) == (3000, 2000)
    assert result.image.startswith("data:image/jpeg;base64,")
    assert str(tmp_path) not in str(result.as_dict())


def test_thumbnail_respects_its_smaller_bounds(tmp_path: Path) -> None:
    source = tmp_path / "portrait.jpg"
    Image.new("RGB", (2000, 3000), "navy").save(source)
    job = _stored_job(tmp_path, source)

    result = build_job_preview(
        job,
        PreviewKind.ORIGINAL,
        bounds=THUMBNAIL_BOUNDS,
        quality=72,
    )

    assert result.available
    assert result.preview_width <= THUMBNAIL_BOUNDS[0]
    assert result.preview_height <= THUMBNAIL_BOUNDS[1]
    assert (result.preview_width, result.preview_height) == (147, 220)


def test_preview_applies_exif_orientation_once(tmp_path: Path) -> None:
    source = tmp_path / "oriented.jpg"
    image = Image.new("RGB", (120, 80), "navy")
    exif = image.getexif()
    exif[274] = 6
    image.save(source, exif=exif)
    job = _stored_job(tmp_path, source)

    result = build_job_preview(job, PreviewKind.ORIGINAL)

    assert (result.width, result.height) == (80, 120)
    assert (result.preview_width, result.preview_height) == (80, 120)


def test_result_preview_is_unavailable_before_output_exists(tmp_path: Path) -> None:
    source = tmp_path / "source.jpg"
    Image.new("RGB", (40, 30), "navy").save(source)
    job = _stored_job(tmp_path, source)

    result = build_job_preview(job, PreviewKind.RESULT)

    assert result == JobPreview.unavailable(
        PreviewKind.RESULT.value,
        PreviewUnavailableReason.OUTPUT_NOT_READY,
    )


def test_result_preview_reports_missing_output(tmp_path: Path) -> None:
    source = tmp_path / "source.jpg"
    output = tmp_path / "车牌已消除" / "source_clean.jpg"
    Image.new("RGB", (40, 30), "navy").save(source)
    job = _stored_job(tmp_path, source, output=output)

    result = build_job_preview(job, PreviewKind.RESULT)

    assert result.reason is PreviewUnavailableReason.OUTPUT_MISSING


def test_original_preview_reports_missing_and_invalid_sources(tmp_path: Path) -> None:
    missing = tmp_path / "missing.jpg"
    missing_job = _stored_job(tmp_path, missing)
    invalid = tmp_path / "invalid.jpg"
    invalid.write_bytes(b"not an image")
    invalid_job = _stored_job(tmp_path / "invalid-db", invalid)

    missing_result = build_job_preview(missing_job, PreviewKind.ORIGINAL)
    invalid_result = build_job_preview(invalid_job, PreviewKind.ORIGINAL)

    assert missing_result.reason is PreviewUnavailableReason.SOURCE_MISSING
    assert invalid_result.reason is PreviewUnavailableReason.DECODE_FAILED
