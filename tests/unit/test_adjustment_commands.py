from uuid import uuid4

import pytest

from app.core.adjustment_commands import resolve_adjustment_commands
from app.domain.detection import BoundingBox, Detection, Quadrilateral


def test_commands_edit_add_remove_and_set_margin() -> None:
    first = Detection(BoundingBox(10, 20, 100, 50), 0.8)
    second = Detection(BoundingBox(120, 20, 200, 50), 0.7)
    new_id = str(uuid4())

    resolved = resolve_adjustment_commands(
        (100, 240),
        [first, second],
        [
            {
                "type": "set_detection_polygon",
                "target_id": "detection:0",
                "points": [[12, 20], [98, 18], [100, 52], [10, 54]],
            },
            {"type": "remove_detection", "target_id": "detection:1"},
            {
                "type": "add_polygon",
                "id": new_id,
                "points": [[120, 30], [200, 28], [202, 55], [118, 57]],
            },
            {"type": "set_margin", "value": -0.1},
        ],
    )

    assert len(resolved.detections) == 2
    assert resolved.detections[0].polygon == Quadrilateral(
        ((12, 20), (98, 18), (100, 52), (10, 54))
    )
    assert resolved.detections[1].confidence == 1
    assert resolved.margin_ratio == -0.1


def test_commands_support_legacy_remove_index() -> None:
    resolved = resolve_adjustment_commands(
        (100, 100),
        [Detection(BoundingBox(10, 10, 40, 30), 0.8)],
        [{"type": "remove_detection", "index": 0}],
    )

    assert resolved.detections == ()
    assert resolved.margin_ratio == 0.35


def test_commands_accept_configured_default_margin() -> None:
    resolved = resolve_adjustment_commands(
        (100, 100),
        [],
        [],
        default_margin_ratio=0.72,
    )

    assert resolved.margin_ratio == 0.72


@pytest.mark.parametrize(
    "command",
    [
        {"type": "set_margin", "value": 1.01},
        {"type": "brush_add", "points": [[1, 2]], "radius": 0},
        {"type": "add_polygon", "id": "not-a-uuid", "points": []},
        {"type": "unknown"},
    ],
)
def test_commands_reject_invalid_input(command: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        resolve_adjustment_commands((100, 100), [], [command])
