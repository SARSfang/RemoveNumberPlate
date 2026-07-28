import pytest

from app.core.mask_builder import PlateMaskPolicy, build_plate_mask
from app.domain.detection import BoundingBox, Detection, Quadrilateral


def test_mask_follows_perspective_polygon_not_bounding_box_corners() -> None:
    polygon = Quadrilateral(((80, 50), (220, 35), (210, 85), (90, 95)))
    detection = Detection(polygon.bounding_box, 0.9, polygon=polygon)

    mask = build_plate_mask((140, 300), [detection], PlateMaskPolicy(0))

    assert mask[60, 150] == 255
    assert mask[36, 81] == 0
    assert mask[94, 219] == 0


def test_mask_default_margin_is_thirty_five_percent() -> None:
    polygon = Quadrilateral(((100, 50), (200, 50), (200, 70), (100, 70)))
    detection = Detection(polygon.bounding_box, 0.9, polygon=polygon)

    mask = build_plate_mask((120, 300), [detection])

    assert mask[43, 150] == 255
    assert mask[42, 150] == 0
    assert mask[60, 93] == 255
    assert mask[60, 92] == 0


def test_mask_supports_negative_margin() -> None:
    detection = Detection(BoundingBox(100, 50, 200, 90), 0.9)

    mask = build_plate_mask((140, 300), [detection], PlateMaskPolicy(-0.15))

    assert mask[70, 150] == 255
    assert mask[51, 150] == 0
    assert mask[70, 101] == 0


def test_mask_clips_expansion_at_image_edges() -> None:
    detection = Detection(BoundingBox(1, 1, 20, 10), 0.9)
    mask = build_plate_mask((30, 30), [detection])

    assert mask.shape == (30, 30)
    assert mask[1, 0] == 255


@pytest.mark.parametrize("ratio", [-0.301, 1.001])
def test_mask_policy_rejects_out_of_range_margin(ratio: float) -> None:
    with pytest.raises(ValueError, match="margin"):
        PlateMaskPolicy(ratio)
