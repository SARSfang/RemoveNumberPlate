"""Persistent batch-job domain types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from uuid import UUID, uuid4


class JobStatus(StrEnum):
    QUEUED = "queued"
    DETECTING = "detecting"
    AUTO_READY = "auto_ready"
    REVIEW_REQUIRED = "review_required"
    NO_PLATE = "no_plate"
    INPAINTING = "inpainting"
    WRITING = "writing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RiskReason(StrEnum):
    LOW_CONFIDENCE = "low_confidence"
    PLATE_TOO_SMALL = "plate_too_small"
    TOUCHES_EDGE = "touches_edge"
    ABNORMAL_BOX = "abnormal_box"
    OVERLAPPING_BOXES = "overlapping_boxes"
    INVALID_COORDINATES = "invalid_coordinates"
    GPU_OUT_OF_MEMORY = "gpu_out_of_memory"
    INPAINT_FAILED = "inpaint_failed"
    WRITE_FAILED = "write_failed"


@dataclass(frozen=True, slots=True)
class ImageJob:
    source: Path
    output: Path
    status: JobStatus = JobStatus.QUEUED
    id: UUID = field(default_factory=uuid4)
    risks: tuple[RiskReason, ...] = ()

    def __post_init__(self) -> None:
        if self.source == self.output:
            raise ValueError("output must not overwrite the source")
