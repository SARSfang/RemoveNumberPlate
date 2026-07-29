from pathlib import Path
from typing import Any

import piexif
from PIL import Image

from app.core.exif_writer import ExifConfig, ExifWriter


def _make_jpeg(path: Path) -> Path:
    Image.new("RGB", (10, 10), (255, 0, 0)).save(path, format="JPEG")
    return path


def _make_png(path: Path) -> Path:
    Image.new("RGB", (10, 10), (255, 0, 0)).save(path, format="PNG")
    return path


def _read_exif(path: Path) -> dict[str, Any]:
    with Image.open(path) as img:
        exif_data = img.info.get("exif")
    return piexif.load(exif_data) if exif_data else {}


def test_disabled_config_copies_image(tmp_path: Path) -> None:
    source = _make_jpeg(tmp_path / "source.jpg")
    original_bytes = source.read_bytes()
    output = tmp_path / "output.jpg"

    writer = ExifWriter(ExifConfig(enabled=False, artist="test artist"))
    result = writer.write(source, output)

    assert result == output
    assert output.read_bytes() == original_bytes


def test_writes_artist_field(tmp_path: Path) -> None:
    source = _make_jpeg(tmp_path / "source.jpg")
    output = tmp_path / "output.jpg"

    writer = ExifWriter(ExifConfig(enabled=True, artist="test artist"))
    writer.write(source, output)

    exif = _read_exif(output)
    assert exif["0th"][piexif.ImageIFD.Artist] == b"test artist"


def test_writes_copyright_field(tmp_path: Path) -> None:
    source = _make_jpeg(tmp_path / "source.jpg")
    output = tmp_path / "output.jpg"

    writer = ExifWriter(ExifConfig(enabled=True, copyright="test copyright"))
    writer.write(source, output)

    exif = _read_exif(output)
    assert exif["0th"][piexif.ImageIFD.Copyright] == b"test copyright"


def test_writes_description_field(tmp_path: Path) -> None:
    source = _make_jpeg(tmp_path / "source.jpg")
    output = tmp_path / "output.jpg"

    writer = ExifWriter(ExifConfig(enabled=True, description="test description"))
    writer.write(source, output)

    exif = _read_exif(output)
    assert exif["0th"][piexif.ImageIFD.ImageDescription] == b"test description"


def test_preserves_existing_exif(tmp_path: Path) -> None:
    source = _make_jpeg(tmp_path / "source.jpg")
    first_output = tmp_path / "first.jpg"
    second_output = tmp_path / "second.jpg"

    ExifWriter(ExifConfig(enabled=True, artist="old artist")).write(source, first_output)
    ExifWriter(ExifConfig(enabled=True, copyright="new copyright")).write(
        first_output, second_output
    )

    exif = _read_exif(second_output)
    assert exif["0th"][piexif.ImageIFD.Artist] == b"old artist"
    assert exif["0th"][piexif.ImageIFD.Copyright] == b"new copyright"


def test_empty_fields_disables(tmp_path: Path) -> None:
    source = _make_jpeg(tmp_path / "source.jpg")
    original_bytes = source.read_bytes()
    output = tmp_path / "output.jpg"

    writer = ExifWriter(ExifConfig(enabled=True))
    writer.write(source, output)

    assert output.read_bytes() == original_bytes


def test_png_skipped(tmp_path: Path) -> None:
    source = _make_png(tmp_path / "source.png")
    original_bytes = source.read_bytes()
    output = tmp_path / "output.png"

    writer = ExifWriter(ExifConfig(enabled=True, artist="test artist"))
    writer.write(source, output)

    assert output.read_bytes() == original_bytes


def test_atomic_write(tmp_path: Path) -> None:
    source = _make_jpeg(tmp_path / "source.jpg")
    output = tmp_path / "output.jpg"

    writer = ExifWriter(ExifConfig(enabled=True, artist="test artist"))
    writer.write(source, output)

    assert output.is_file()
    with Image.open(output) as img:
        img.verify()
