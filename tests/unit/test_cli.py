from pathlib import Path

from app.cli import report_as_mapping
from app.core.batch import BatchItemResult, BatchReport
from app.domain.job import JobStatus
from app.domain.result import ProcessingResult


def test_cli_report_contains_batch_counts_without_ocr_data() -> None:
    report = BatchReport(
        (
            BatchItemResult(
                Path("source.jpg"),
                ProcessingResult(
                    Path("out.jpg"),
                    1.25,
                    status=JobStatus.COMPLETED,
                    detection_count=1,
                ),
            ),
        ),
        1.5,
    )

    value = report_as_mapping(report)

    assert value["completed"] == 1
    assert value["items"][0]["output"] == "out.jpg"
    assert "plate_text" not in value["items"][0]
