from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.core.image_io import (
    OUTPUT_DIRECTORY_NAME,
    allocate_output_path,
    discover_images,
    load_image,
    write_image_atomic,
)


def test_discover_images_filters_formats_outputs_and_duplicates(tmp_path: Path) -> None:
    first = tmp_path / "A.JPG"
    second = tmp_path / "nested" / "b.tiff"
    output = tmp_path / OUTPUT_DIRECTORY_NAME / "ignored.jpg"
    second.parent.mkdir()
    output.parent.mkdir()
    first.write_bytes(b"x")
    second.write_bytes(b"x")
    output.write_bytes(b"x")

    result = discover_images([tmp_path, first])

    assert result == [first.resolve(), second.resolve()]


def test_allocate_output_path_never_reuses_existing_name(tmp_path: Path) -> None:
    source = tmp_path / "photo.jpg"
    output_dir = tmp_path / OUTPUT_DIRECTORY_NAME
    output_dir.mkdir()
    (output_dir / "photo_clean.jpg").write_bytes(b"existing")

    result = allocate_output_path(source)

    assert result.name == "photo_clean_2.jpg"


def test_load_image_applies_orientation_once(tmp_path: Path) -> None:
    source = tmp_path / "oriented.jpg"
    image = Image.new("RGB", (4, 2), (20, 40, 60))
    exif = image.getexif()
    exif[274] = 6
    image.save(source, exif=exif)

    loaded = load_image(source)

    assert loaded.pixels_rgb.shape == (4, 2, 3)
    if loaded.exif is not None:
        normalized_exif = Image.Exif()
        normalized_exif.load(loaded.exif)
        assert 274 not in normalized_exif


@pytest.mark.parametrize(
    ("suffix", "image_format"),
    [(".jpg", "JPEG"), (".png", "PNG"), (".tiff", "TIFF")],
)
def test_atomic_write_round_trips_supported_formats(
    tmp_path: Path,
    suffix: str,
    image_format: str,
) -> None:
    source = tmp_path / f"source{suffix}"
    Image.new("RGB", (24, 16), (10, 20, 30)).save(source, format=image_format)
    loaded = load_image(source)
    output = allocate_output_path(source)

    written = write_image_atomic(loaded, loaded.pixels_rgb, output)

    assert written.is_file()
    with Image.open(written) as result:
        assert result.size == (24, 16)


def test_atomic_write_refuses_existing_target(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (4, 4)).save(source)
    loaded = load_image(source)
    output = tmp_path / "existing.png"
    output.write_bytes(b"do not replace")

    with pytest.raises(FileExistsError):
        write_image_atomic(loaded, np.zeros((4, 4, 3), dtype=np.uint8), output)

    assert output.read_bytes() == b"do not replace"


def test_atomic_write_preserves_safe_exif_and_dpi(tmp_path: Path) -> None:
    source = tmp_path / "metadata.jpg"
    image = Image.new("RGB", (20, 10), (10, 20, 30))
    exif = image.getexif()
    exif[274] = 1
    exif[36867] = "2026:07:28 10:20:30"
    image.save(source, exif=exif, dpi=(300, 300), icc_profile=b"test-icc")
    loaded = load_image(source)
    output = allocate_output_path(source)

    write_image_atomic(loaded, loaded.pixels_rgb, output)

    with Image.open(output) as result:
        assert result.getexif().get(36867) == "2026:07:28 10:20:30"
        assert 274 not in result.getexif()
        assert result.info.get("icc_profile") == b"test-icc"
        assert result.info["dpi"][0] == pytest.approx(300, abs=1)
