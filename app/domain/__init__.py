"""Domain objects shared by the pipeline and GUI."""

from app.domain.detection import BoundingBox, Detection
from app.domain.job import ImageJob, JobStatus, RiskReason
from app.domain.result import ProcessingResult

__all__ = [
    "BoundingBox",
    "Detection",
    "ImageJob",
    "JobStatus",
    "ProcessingResult",
    "RiskReason",
]
