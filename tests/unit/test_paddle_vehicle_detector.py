import numpy as np
import pytest

from app.infrastructure.paddle_vehicle_detector import (
    decode_vehicle_boxes,
    preprocess_vehicle_image,
)


def test_preprocess_vehicle_image_matches_model_contract() -> None:
    image = np.full((320, 800, 3), 255, dtype=np.uint8)

    tensor, scale_factor = preprocess_vehicle_image(image)

    assert tensor.shape == (1, 3, 640, 640)
    assert tensor.dtype == np.float32
    np.testing.assert_allclose(scale_factor, [[2.0, 0.8]])


def test_preprocess_vehicle_image_rejects_wrong_dtype() -> None:
    with pytest.raises(ValueError):
        preprocess_vehicle_image(np.zeros((10, 10, 3), dtype=np.float32))


def test_decode_vehicle_boxes_clips_and_filters() -> None:
    boxes = np.array(
        [
            [0, 0.9, -5, 10, 120, 90],
            [0, 0.2, 10, 10, 20, 20],
            [0, 0.8, 50, 20, 40, 30],
        ],
        dtype=np.float32,
    )

    detections = decode_vehicle_boxes(boxes, (100, 100), confidence_threshold=0.5)

    assert len(detections) == 1
    assert detections[0].box.x1 == 0
    assert detections[0].box.x2 == 100
