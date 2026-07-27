import pytest

from app.domain.detection import BoundingBox, Detection


def test_bounding_box_properties() -> None:
    box = BoundingBox(10, 20, 50, 60)

    assert box.width == 40
    assert box.height == 40
    assert box.area == 1600


def test_bounding_box_clips_to_image() -> None:
    box = BoundingBox(10, 20, 150, 160)

    assert box.clipped(100, 120) == BoundingBox(10, 20, 100, 120)


@pytest.mark.parametrize(
    "coordinates",
    [
        (-1, 0, 10, 10),
        (0, -1, 10, 10),
        (10, 0, 10, 10),
        (0, 10, 10, 10),
    ],
)
def test_bounding_box_rejects_invalid_coordinates(
    coordinates: tuple[int, int, int, int],
) -> None:
    with pytest.raises(ValueError):
        BoundingBox(*coordinates)


def test_detection_rejects_invalid_confidence() -> None:
    with pytest.raises(ValueError):
        Detection(BoundingBox(0, 0, 10, 10), 1.01)
