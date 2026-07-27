from app.core.risk_gate import assess_detection_risks
from app.domain.detection import BoundingBox, Detection
from app.domain.job import RiskReason


def test_high_confidence_normal_plate_has_no_risk() -> None:
    detections = [Detection(BoundingBox(200, 300, 400, 360), 0.9)]
    assert assess_detection_risks((1000, 1200), detections) == ()


def test_low_confidence_tiny_edge_plate_collects_risks() -> None:
    detections = [Detection(BoundingBox(0, 0, 8, 4), 0.2)]
    risks = assess_detection_risks((1000, 1200), detections)
    assert RiskReason.LOW_CONFIDENCE in risks
    assert RiskReason.PLATE_TOO_SMALL in risks
    assert RiskReason.TOUCHES_EDGE in risks


def test_overlapping_detections_require_review() -> None:
    detections = [
        Detection(BoundingBox(100, 100, 300, 160), 0.9),
        Detection(BoundingBox(110, 105, 295, 158), 0.9),
    ]
    risks = assess_detection_risks((800, 1000), detections)
    assert RiskReason.OVERLAPPING_BOXES in risks
