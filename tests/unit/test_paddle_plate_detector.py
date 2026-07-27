import numpy as np
import pytest

from app.infrastructure.paddle_plate_detector import (
    decode_db_map,
    normalize_for_db,
    resize_for_db,
)


def test_resize_for_db_preserves_shape_metadata() -> None:
    image = np.zeros((400, 800, 3), dtype=np.uint8)

    resized, shape = resize_for_db(image, limit_side_len=640, limit_type="max")

    assert resized.shape == (320, 640, 3)
    assert shape == (400, 800, 0.8, 0.8)


def test_resize_for_db_rejects_unknown_limit_type() -> None:
    image = np.zeros((64, 64, 3), dtype=np.uint8)

    with pytest.raises(ValueError, match="limit_type"):
        resize_for_db(image, limit_type="unknown")


def test_normalize_for_db_returns_nchw_float32() -> None:
    image = np.zeros((32, 64, 3), dtype=np.uint8)

    tensor = normalize_for_db(image)

    assert tensor.shape == (1, 3, 32, 64)
    assert tensor.dtype == np.float32
    assert tensor.flags.c_contiguous


def test_decode_db_map_returns_source_scaled_detection() -> None:
    probability = np.zeros((64, 128), dtype=np.float32)
    probability[24:40, 32:96] = 0.95

    detections = decode_db_map(probability, (128, 256, 0.5, 0.5))

    assert len(detections) == 1
    detection = detections[0]
    assert detection.confidence > 0.9
    assert detection.box.x1 < 64
    assert detection.box.x2 > 192
    assert detection.box.y1 < 48
    assert detection.box.y2 > 80
