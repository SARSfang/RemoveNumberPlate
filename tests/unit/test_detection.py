import pytest

from app.domain.detection import BoundingBox, Detection, Quadrilateral


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


def test_quadrilateral_properties_and_box_fallback() -> None:
    polygon = Quadrilateral(((10, 20), (80, 15), (90, 50), (5, 55)))
    detection = Detection(polygon.bounding_box, 0.9, polygon=polygon)

    assert polygon.area == pytest.approx(2725)
    assert polygon.bounding_box == BoundingBox(5, 15, 90, 55)
    assert detection.effective_polygon is polygon
    assert Detection(BoundingBox(1, 2, 3, 4), 0.5).effective_polygon == (
        Quadrilateral(((1, 2), (3, 2), (3, 4), (1, 4)))
    )


@pytest.mark.parametrize(
    "points",
    [
        ((0, 0), (10, 10), (0, 10), (10, 0)),
        ((0, 0), (10, 0), (5, 0), (0, 10)),
        ((0, 0), (0, 10), (10, 10), (10, 0)),
    ],
)
def test_quadrilateral_rejects_invalid_order_or_shape(
    points: tuple[tuple[int, int], ...],
) -> None:
    with pytest.raises(ValueError):
        Quadrilateral(points)  # type: ignore[arg-type]


def test_quadrilateral_clips_to_image() -> None:
    polygon = Quadrilateral(((10, 10), (150, 5), (160, 120), (5, 130)))

    assert polygon.clipped(100, 80) == Quadrilateral(
        ((10, 10), (100, 5), (100, 80), (5, 80))
    )
