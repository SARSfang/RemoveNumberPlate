import numpy as np
import pytest

from app.infrastructure.migan_inpainter import (
    InpainterError,
    finalize_migan_output,
    prepare_migan_inputs,
)


def test_prepare_migan_inputs_inverts_remove_mask() -> None:
    image = np.zeros((2, 3, 3), dtype=np.uint8)
    mask = np.array([[0, 255, 1], [0, 0, 0]], dtype=np.uint8)

    image_tensor, mask_tensor = prepare_migan_inputs(image, mask)

    assert image_tensor.shape == (1, 3, 2, 3)
    np.testing.assert_array_equal(mask_tensor[0, 0], [[255, 0, 0], [255, 255, 255]])


def test_prepare_migan_inputs_requires_matching_mask() -> None:
    image = np.zeros((10, 10, 3), dtype=np.uint8)
    with pytest.raises(ValueError, match="dimensions"):
        prepare_migan_inputs(image, np.zeros((8, 10), dtype=np.uint8))


def test_finalize_migan_output_changes_only_selected_pixels() -> None:
    image = np.full((2, 2, 3), 10, dtype=np.uint8)
    output = np.full((1, 3, 2, 2), 200, dtype=np.uint8)
    mask = np.array([[0, 255], [0, 0]], dtype=np.uint8)

    result = finalize_migan_output(output, image, mask)

    np.testing.assert_array_equal(result[0, 0], [10, 10, 10])
    np.testing.assert_array_equal(result[0, 1], [200, 200, 200])


def test_finalize_migan_output_rejects_wrong_shape() -> None:
    image = np.zeros((2, 2, 3), dtype=np.uint8)
    with pytest.raises(InpainterError, match="output shape"):
        finalize_migan_output(
            np.zeros((1, 3, 1, 1), dtype=np.uint8),
            image,
            np.zeros((2, 2), dtype=np.uint8),
        )
