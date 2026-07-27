import numpy as np

from app.core.mask_builder import PlateMaskPolicy, build_plate_mask
from app.domain.detection import BoundingBox, Detection


def test_mask_expands_horizontally_to_cover_non_text_plate_parts() -> None:
    detection = Detection(BoundingBox(100, 50, 200, 70), 0.9)
    mask = build_plate_mask(
        (120, 300),
        [detection],
        PlateMaskPolicy(
            left_by_height=0.75,
            right_by_height=0.75,
            top_by_height=0.2,
            bottom_by_height=0.2,
        ),
    )

    assert np.all(mask[46:74, 85:215] == 255)
    assert mask[45, 84] == 0


def test_mask_clips_expansion_at_image_edges() -> None:
    detection = Detection(BoundingBox(1, 1, 20, 10), 0.9)
    mask = build_plate_mask((30, 30), [detection])
    assert mask.shape == (30, 30)
    assert mask[0, 0] == 255
