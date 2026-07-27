"""Pipeline result values."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.domain.job import RiskReason


@dataclass(frozen=True, slots=True)
class ProcessingResult:
    output: Path | None
    elapsed_seconds: float
    risks: tuple[RiskReason, ...] = ()

    def __post_init__(self) -> None:
        if self.elapsed_seconds < 0:
            raise ValueError("elapsed_seconds must be non-negative")
