import numpy as np

from app.infrastructure.lama_inpainter import (
    LamaInpainter,
    _context_bounds,
    _feathered_composite,
    split_mask_regions,
)


def test_context_bounds_are_square_and_inside_image() -> None:
    mask = np.zeros((100, 200), dtype=np.uint8)
    mask[40:50, 180:195] = 255
    x1, y1, x2, y2 = _context_bounds(mask, 4)
    assert x2 - x1 == y2 - y1
    assert 0 <= x1 < x2 <= 200
    assert 0 <= y1 < y2 <= 100


def test_feathered_composite_replaces_mask_core() -> None:
    original = np.zeros((40, 40, 3), dtype=np.uint8)
    generated = np.full_like(original, 200)
    mask = np.zeros((40, 40), dtype=np.uint8)
    mask[10:30, 10:30] = 255
    result = _feathered_composite(original, generated, mask, 3)
    np.testing.assert_array_equal(result[20, 20], [200, 200, 200])
    np.testing.assert_array_equal(result[0, 0], [0, 0, 0])


def test_feathered_composite_uses_gradual_boundary() -> None:
    original = np.zeros((60, 60, 3), dtype=np.uint8)
    generated = np.full_like(original, 200)
    mask = np.zeros((60, 60), dtype=np.uint8)
    mask[15:45, 15:45] = 255

    result = _feathered_composite(original, generated, mask, 7)

    assert 0 < result[15, 30, 0] < 200
    assert result[30, 30, 0] == 200


def test_split_mask_regions_splits_distant_regions() -> None:
    mask = np.zeros((100, 100), dtype=np.uint8)
    mask[10:20, 10:20] = 255
    mask[70:80, 70:80] = 255

    regions = split_mask_regions(mask)

    assert len(regions) == 2
    for region in regions:
        points = np.flatnonzero(region)
        assert points.size == 100


def test_split_mask_regions_merges_touching() -> None:
    mask = np.zeros((50, 50), dtype=np.uint8)
    mask[10:20, 10:20] = 255
    mask[19:30, 19:30] = 255

    regions = split_mask_regions(mask)

    assert len(regions) == 1
    np.testing.assert_array_equal(regions[0], mask)


def test_split_mask_regions_returns_empty_for_blank() -> None:
    mask = np.zeros((40, 40), dtype=np.uint8)
    assert split_mask_regions(mask) == []


def test_inpaint_processes_each_region_separately(monkeypatch) -> None:
    inpainter = LamaInpainter.__new__(LamaInpainter)

    def fake_inpaint_crop(self, image_rgb, region):
        result = image_rgb.copy()
        result[region > 0] = 128
        return result

    monkeypatch.setattr(LamaInpainter, "_inpaint_crop", fake_inpaint_crop)

    image = np.zeros((100, 100, 3), dtype=np.uint8)
    mask = np.zeros((100, 100), dtype=np.uint8)
    mask[10:20, 10:20] = 255
    mask[70:80, 70:80] = 255

    result = inpainter.inpaint(image, mask)

    np.testing.assert_array_equal(result[15, 15], [128, 128, 128])
    np.testing.assert_array_equal(result[75, 75], [128, 128, 128])
    np.testing.assert_array_equal(result[50, 50], [0, 0, 0])


def test_inpaint_single_region_uses_single_crop(monkeypatch) -> None:
    inpainter = LamaInpainter.__new__(LamaInpainter)
    calls: list[tuple[object, object]] = []

    def fake_inpaint_crop(self, image_rgb, region):
        calls.append((image_rgb, region))
        return image_rgb.copy()

    monkeypatch.setattr(LamaInpainter, "_inpaint_crop", fake_inpaint_crop)

    image = np.zeros((40, 40, 3), dtype=np.uint8)
    mask = np.zeros((40, 40), dtype=np.uint8)
    mask[10:30, 10:30] = 255

    inpainter.inpaint(image, mask)

    assert len(calls) == 1
