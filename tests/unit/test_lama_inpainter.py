import numpy as np

from app.infrastructure.lama_inpainter import _context_bounds, _feathered_composite


def test_context_bounds_are_square_and_inside_image() -> None:
    mask = np.zeros((100, 200), dtype=np.uint8)
    mask[40:50, 180:195] = 255
    x1, y1, x2, y2 = _context_bounds(mask, 4)
    assert x2 - x1 == y2 - y1
    assert 0 <= x1 < x2 <= 200
    assert 0 <= y1 < y2 <= 100


def test_feathered_composite_replaces_mask_core() -> None:
    original = np.zeros((20, 20, 3), dtype=np.uint8)
    generated = np.full_like(original, 200)
    mask = np.zeros((20, 20), dtype=np.uint8)
    mask[8:12, 8:12] = 255
    result = _feathered_composite(original, generated, mask, 3)
    np.testing.assert_array_equal(result[9, 9], [200, 200, 200])
    np.testing.assert_array_equal(result[0, 0], [0, 0, 0])
