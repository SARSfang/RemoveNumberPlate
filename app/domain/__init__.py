"""Domain objects shared by the pipeline and GUI."""

from app.domain.detection import BoundingBox, Detection, Quadrilateral
from app.domain.job import ImageJob, JobStatus, RiskReason
from app.domain.result import ProcessingResult

__all__ = [
    "BoundingBox",
    "Detection",
    "Quadrilateral",
    "ImageJob",
    "JobStatus",
    "ProcessingResult",
    "RiskReason",
]
