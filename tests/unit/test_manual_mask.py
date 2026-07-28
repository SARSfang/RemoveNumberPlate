import numpy as np

from app.core.manual_mask import build_manual_mask
from app.domain.detection import BoundingBox, Detection


def test_manual_mask_can_remove_auto_detection_and_add_rectangle() -> None:
    detection = Detection(BoundingBox(20, 20, 60, 35), 0.5)

    mask = build_manual_mask(
        (100, 120),
        [detection],
        [
            {"type": "remove_detection", "index": 0},
            {"type": "rectangle", "start": [70, 40], "end": [100, 70]},
        ],
    )

    assert mask[25, 30] == 0
    assert np.all(mask[40:71, 70:101] == 255)


def test_manual_brush_add_and_erase_use_source_coordinates() -> None:
    mask = build_manual_mask(
        (100, 100),
        [],
        [
            {
                "type": "brush_add",
                "points": [[20, 50], [80, 50]],
                "radius": 10,
            },
            {
                "type": "brush_erase",
                "points": [[50, 50]],
                "radius": 4,
            },
        ],
    )

    assert mask[50, 25] == 255
    assert mask[50, 50] == 0
    assert mask[10, 10] == 0


def test_manual_mask_clips_out_of_bounds_commands() -> None:
    mask = build_manual_mask(
        (20, 30),
        [],
        [{"type": "rectangle", "start": [-20, -30], "end": [100, 90]}],
    )

    assert np.all(mask == 255)


def test_manual_mask_uses_edited_perspective_polygon() -> None:
    detection = Detection(BoundingBox(20, 20, 80, 50), 0.8)

    mask = build_manual_mask(
        (100, 120),
        [detection],
        [
            {
                "type": "set_detection_polygon",
                "target_id": "detection:0",
                "points": [[20, 30], [80, 20], [75, 50], [25, 60]],
            },
            {"type": "set_margin", "value": 0},
        ],
    )

    assert mask[40, 50] == 255
    assert mask[21, 21] == 0
    assert mask[59, 79] == 0
