"""Pipeline result values."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.domain.job import JobStatus, RiskReason


@dataclass(frozen=True, slots=True)
class ProcessingResult:
    output: Path | None
    elapsed_seconds: float
    risks: tuple[RiskReason, ...] = ()
    status: JobStatus = JobStatus.COMPLETED
    detection_count: int = 0
    error: str | None = None

    def __post_init__(self) -> None:
        if self.elapsed_seconds < 0:
            raise ValueError("elapsed_seconds must be non-negative")
        if self.detection_count < 0:
            raise ValueError("detection_count must be non-negative")
        if self.output is not None and self.status is not JobStatus.COMPLETED:
            raise ValueError("only completed results may contain an output path")
