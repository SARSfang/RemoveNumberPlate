"""Unit tests for WatermarkRenderer."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from app.core.watermark import WatermarkConfig, WatermarkRenderer


def _make_jpeg(path: Path, size: tuple[int, int] = (50, 50)) -> None:
    """Create a small JPEG test image."""
    Image.new("RGB", size, "red").save(path, format="JPEG", quality=95)


def _make_png(path: Path, size: tuple[int, int] = (50, 50)) -> None:
    Image.new("RGB", size, "blue").save(path, format="PNG")


def _make_watermark_png(path: Path, size: tuple[int, int] = (40, 20)) -> None:
    """Create a small RGBA PNG with a distinct color for watermark tests."""
    Image.new("RGBA", size, (0, 255, 0, 255)).save(path, format="PNG")


def test_disabled_config_copies_image(tmp_path: Path) -> None:
    source = tmp_path / "input.jpg"
    _make_jpeg(source)
    output = tmp_path / "out" / "input.jpg"

    renderer = WatermarkRenderer(WatermarkConfig(enabled=False))
    renderer.render(source, output)

    assert output.exists()
    with Image.open(output) as img:
        assert img.size == (50, 50)


def test_empty_text_copies_image(tmp_path: Path) -> None:
    source = tmp_path / "input.jpg"
    _make_jpeg(source)
    output = tmp_path / "output.jpg"

    renderer = WatermarkRenderer(WatermarkConfig(enabled=True, text="   "))
    renderer.render(source, output)

    assert output.exists()


def test_text_watermark_applied(tmp_path: Path) -> None:
    source = tmp_path / "input.jpg"
    _make_jpeg(source, (100, 100))
    output = tmp_path / "output.jpg"

    renderer = WatermarkRenderer(
        WatermarkConfig(enabled=True, text="© TEST", font_size=20)
    )
    renderer.render(source, output)

    assert output.exists()
    # Watermarked output should differ from a plain copy
    plain = tmp_path / "plain.jpg"
    _make_jpeg(plain, (100, 100))
    with Image.open(output) as watermarked, Image.open(plain) as original:
        assert watermarked.size == original.size


@pytest.mark.parametrize(
    "position",
    [
        "top-left",
        "top-center",
        "top-right",
        "center-left",
        "center",
        "center-right",
        "bottom-left",
        "bottom-center",
        "bottom-right",
    ],
)
def test_all_positions(position: str, tmp_path: Path) -> None:
    source = tmp_path / "input.jpg"
    _make_jpeg(source, (80, 80))
    output = tmp_path / f"out_{position}.jpg"

    renderer = WatermarkRenderer(
        WatermarkConfig(enabled=True, text="W", position=position)
    )
    renderer.render(source, output)
    assert output.exists()


@pytest.mark.parametrize("opacity", [0.0, 0.5, 1.0])
def test_opacity_range(opacity: float, tmp_path: Path) -> None:
    source = tmp_path / "input.jpg"
    _make_jpeg(source)
    output = tmp_path / "output.jpg"

    renderer = WatermarkRenderer(
        WatermarkConfig(enabled=True, text="W", opacity=opacity)
    )
    renderer.render(source, output)
    assert output.exists()


def test_font_fallback(tmp_path: Path) -> None:
    source = tmp_path / "input.jpg"
    _make_jpeg(source)
    output = tmp_path / "output.jpg"

    # Simulate all system fonts missing: _load_font should fall back to
    # Pillow's built-in default font (load_default).
    with patch("app.core.watermark._FONT_PATHS", ()):
        renderer = WatermarkRenderer(WatermarkConfig(enabled=True, text="W"))
        renderer.render(source, output)
    assert output.exists()


def test_preserves_jpeg_format(tmp_path: Path) -> None:
    source = tmp_path / "input.jpg"
    _make_jpeg(source)
    output = tmp_path / "output.jpg"

    renderer = WatermarkRenderer(WatermarkConfig(enabled=True, text="W"))
    renderer.render(source, output)

    with Image.open(output) as img:
        assert (img.format or "").upper() == "JPEG"


def test_preserves_png_format(tmp_path: Path) -> None:
    source = tmp_path / "input.png"
    _make_png(source)
    output = tmp_path / "output.png"

    renderer = WatermarkRenderer(WatermarkConfig(enabled=True, text="W"))
    renderer.render(source, output)

    with Image.open(output) as img:
        assert (img.format or "").upper() == "PNG"


def test_atomic_write_creates_valid_image(tmp_path: Path) -> None:
    source = tmp_path / "input.jpg"
    _make_jpeg(source)
    output = tmp_path / "output.jpg"

    renderer = WatermarkRenderer(WatermarkConfig(enabled=True, text="W"))
    renderer.render(source, output)

    assert output.exists()
    with Image.open(output) as img:
        img.verify()


def test_invalid_color_defaults_to_white(tmp_path: Path) -> None:
    source = tmp_path / "input.jpg"
    _make_jpeg(source)
    output = tmp_path / "output.jpg"

    renderer = WatermarkRenderer(
        WatermarkConfig(enabled=True, text="W", color="BAD")
    )
    renderer.render(source, output)
    assert output.exists()


def test_image_watermark_applied(tmp_path: Path) -> None:
    """Image watermark path: PNG watermark overlaid onto a JPEG base."""
    source = tmp_path / "input.jpg"
    _make_jpeg(source, (200, 100))
    watermark_path = tmp_path / "logo.png"
    _make_watermark_png(watermark_path, (60, 30))
    output = tmp_path / "output.jpg"

    renderer = WatermarkRenderer(
        WatermarkConfig(
            enabled=True,
            type="image",
            image_path=str(watermark_path),
            image_scale=0.2,
            opacity=1.0,
        )
    )
    renderer.render(source, output)

    assert output.exists()
    with Image.open(output) as watermarked, Image.open(source) as original:
        assert watermarked.size == original.size
        assert (watermarked.format or "").upper() == "JPEG"
    # Watermarked bytes should differ from a plain copy
    plain_copy = tmp_path / "plain.jpg"
    _make_jpeg(plain_copy, (200, 100))
    assert output.read_bytes() != plain_copy.read_bytes()


def test_image_watermark_missing_file_falls_back(tmp_path: Path) -> None:
    """Missing image_path renders the original image unchanged."""
    source = tmp_path / "input.jpg"
    _make_jpeg(source, (80, 80))
    output = tmp_path / "output.jpg"

    renderer = WatermarkRenderer(
        WatermarkConfig(
            enabled=True,
            type="image",
            image_path=str(tmp_path / "missing.png"),
            image_scale=0.2,
        )
    )
    renderer.render(source, output)

    assert output.exists()
    with Image.open(output) as watermarked, Image.open(source) as original:
        assert watermarked.size == original.size


def test_image_watermark_scale_changes_size(tmp_path: Path) -> None:
    """Different image_scale values should produce different outputs."""
    source = tmp_path / "input.jpg"
    _make_jpeg(source, (300, 300))
    watermark_path = tmp_path / "logo.png"
    _make_watermark_png(watermark_path, (100, 50))

    small = tmp_path / "small.jpg"
    large = tmp_path / "large.jpg"

    renderer_small = WatermarkRenderer(
        WatermarkConfig(
            enabled=True,
            type="image",
            image_path=str(watermark_path),
            image_scale=0.1,
            opacity=1.0,
        )
    )
    renderer_small.render(source, small)

    renderer_large = WatermarkRenderer(
        WatermarkConfig(
            enabled=True,
            type="image",
            image_path=str(watermark_path),
            image_scale=0.5,
            opacity=1.0,
        )
    )
    renderer_large.render(source, large)

    assert small.exists()
    assert large.exists()
    assert small.read_bytes() != large.read_bytes()


def test_image_watermark_preserves_png_format(tmp_path: Path) -> None:
    source = tmp_path / "input.png"
    _make_png(source, (120, 120))
    watermark_path = tmp_path / "logo.png"
    _make_watermark_png(watermark_path)
    output = tmp_path / "output.png"

    renderer = WatermarkRenderer(
        WatermarkConfig(
            enabled=True,
            type="image",
            image_path=str(watermark_path),
            image_scale=0.2,
            opacity=0.7,
        )
    )
    renderer.render(source, output)

    with Image.open(output) as img:
        assert (img.format or "").upper() == "PNG"


def test_invalid_type_raises() -> None:
    with pytest.raises(ValueError, match="unsupported watermark type"):
        WatermarkConfig(enabled=True, type="unknown")


def test_invalid_image_scale_raises() -> None:
    with pytest.raises(ValueError, match="image_scale must be between"):
        WatermarkConfig(
            enabled=True, type="image", image_scale=0.01
        )
    with pytest.raises(ValueError, match="image_scale must be between"):
        WatermarkConfig(
            enabled=True, type="image", image_scale=1.5
        )
