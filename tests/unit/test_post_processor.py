"""Unit tests for PostProcessor coordinator."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import piexif
from PIL import Image

from app.core.exif_writer import ExifConfig
from app.core.post_processor import PostProcessor
from app.core.watermark import WatermarkConfig
from app.settings import PostProcessConfig


def _make_jpeg(path: Path, size: tuple[int, int] = (50, 50)) -> Path:
    """Create a small JPEG test image."""
    Image.new("RGB", size, "red").save(path, format="JPEG", quality=95)
    return path


def test_disabled_returns_original(tmp_path: Path) -> None:
    source = _make_jpeg(tmp_path / "input.jpg")
    removal_output = _make_jpeg(tmp_path / "removal.jpg")

    processor = PostProcessor(PostProcessConfig(enabled=False))
    result = processor.process(source, removal_output, sequence=1)

    assert result == removal_output


def test_naming_only_renames(tmp_path: Path) -> None:
    source = _make_jpeg(tmp_path / "input.jpg")
    removal_output = _make_jpeg(tmp_path / "removal.jpg")

    processor = PostProcessor(
        PostProcessConfig(
            enabled=True,
            naming_template="{original}_clean{ext}",
        )
    )
    result = processor.process(source, removal_output, sequence=1)

    assert result == removal_output.parent / "input_clean.jpg"
    assert result.exists()
    # 原始 removal_output 保留
    assert removal_output.exists()


def test_watermark_only_applies_watermark(tmp_path: Path) -> None:
    source = _make_jpeg(tmp_path / "input.jpg")
    removal_output = _make_jpeg(tmp_path / "removal.jpg")

    processor = PostProcessor(
        PostProcessConfig(
            enabled=True,
            naming_template="{original}_wm{ext}",
            watermark=WatermarkConfig(enabled=True, text="W"),
        )
    )
    result = processor.process(source, removal_output, sequence=1)

    # 模板生成 input_wm.jpg，不与 source / removal_output 冲突
    assert result == removal_output.parent / "input_wm.jpg"
    assert result.exists()
    with Image.open(result) as img:
        img.verify()


def test_exif_only_writes_exif(tmp_path: Path) -> None:
    source = _make_jpeg(tmp_path / "input.jpg")
    removal_output = _make_jpeg(tmp_path / "removal.jpg")

    processor = PostProcessor(
        PostProcessConfig(
            enabled=True,
            naming_template="{original}_exif{ext}",
            exif=ExifConfig(enabled=True, artist="test artist"),
        )
    )
    result = processor.process(source, removal_output, sequence=1)

    assert result == removal_output.parent / "input_exif.jpg"
    assert result.exists()
    with Image.open(result) as img:
        exif_data = img.info.get("exif")
    assert exif_data
    exif_dict = piexif.load(exif_data)
    assert exif_dict["0th"][piexif.ImageIFD.Artist] == b"test artist"


def test_full_pipeline_naming_watermark_exif(tmp_path: Path) -> None:
    source = _make_jpeg(tmp_path / "input.jpg")
    removal_output = _make_jpeg(tmp_path / "removal.jpg")

    processor = PostProcessor(
        PostProcessConfig(
            enabled=True,
            naming_template="{client}_{seq:03}{ext}",
            watermark=WatermarkConfig(enabled=True, text="© TEST"),
            exif=ExifConfig(enabled=True, artist="tester", copyright="© 2026"),
        )
    )
    result = processor.process(source, removal_output, sequence=5, client="acme")

    assert result == removal_output.parent / "acme_005.jpg"
    assert result.exists()
    with Image.open(result) as img:
        exif_data = img.info.get("exif")
    assert exif_data
    exif_dict = piexif.load(exif_data)
    assert exif_dict["0th"][piexif.ImageIFD.Artist] == b"tester"
    assert exif_dict["0th"][piexif.ImageIFD.Copyright] == "© 2026".encode()


def test_failure_falls_back_to_original(tmp_path: Path) -> None:
    source = _make_jpeg(tmp_path / "input.jpg")
    removal_output = _make_jpeg(tmp_path / "removal.jpg")

    processor = PostProcessor(
        PostProcessConfig(
            enabled=True,
            naming_template="{original}_clean{ext}",
        )
    )
    # 模拟 copy2 抛出异常 → 应捕获并返回 removal_output
    with patch("app.core.post_processor.shutil.copy2", side_effect=OSError("disk full")):
        result = processor.process(source, removal_output, sequence=1)

    assert result == removal_output


def test_naming_conflict_resolution(tmp_path: Path) -> None:
    source = _make_jpeg(tmp_path / "input.jpg")
    removal_output = _make_jpeg(tmp_path / "removal.jpg")
    # 预先占用默认目标名 → 应得到 input_clean_2.jpg
    _make_jpeg(tmp_path / "input_clean.jpg")

    processor = PostProcessor(
        PostProcessConfig(
            enabled=True,
            naming_template="{original}_clean{ext}",
        )
    )
    result = processor.process(source, removal_output, sequence=1)

    assert result == removal_output.parent / "input_clean_2.jpg"
    assert result.exists()
