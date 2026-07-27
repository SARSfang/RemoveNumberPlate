"""Metadata-aware image loading and verified atomic output."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageOps, JpegImagePlugin, UnidentifiedImageError

SUPPORTED_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".tif", ".tiff"})
OUTPUT_DIRECTORY_NAME = "车牌已消除"


class ImageIOError(RuntimeError):
    """An image could not be decoded or safely written."""


@dataclass(frozen=True, slots=True)
class LoadedImage:
    pixels_rgb: NDArray[np.uint8]
    source_format: str
    exif: bytes | None
    icc_profile: bytes | None
    dpi: tuple[float, float] | None
    jpeg_qtables: list[list[int]] | None
    jpeg_subsampling: int | None


def discover_images(paths: list[Path]) -> list[Path]:
    """Return stable, de-duplicated supported inputs while skipping outputs."""

    discovered: dict[str, Path] = {}
    for path in paths:
        candidates = [path] if path.is_file() else path.rglob("*") if path.is_dir() else []
        for candidate in candidates:
            if (
                candidate.is_file()
                and candidate.suffix.lower() in SUPPORTED_SUFFIXES
                and OUTPUT_DIRECTORY_NAME not in candidate.parts
            ):
                resolved = candidate.resolve()
                discovered[str(resolved).casefold()] = resolved
    return sorted(discovered.values(), key=lambda value: str(value).casefold())


def load_image(path: Path) -> LoadedImage:
    """Decode, apply EXIF orientation once, and retain safe metadata."""

    try:
        with Image.open(path) as source:
            source.load()
            source_format = (source.format or path.suffix.lstrip(".")).upper()
            icc_profile = source.info.get("icc_profile")
            dpi_value = source.info.get("dpi")
            dpi = (
                (float(dpi_value[0]), float(dpi_value[1]))
                if isinstance(dpi_value, tuple) and len(dpi_value) == 2
                else None
            )
            qtables = None
            subsampling = None
            quantization = getattr(source, "quantization", None)
            if source_format == "JPEG" and isinstance(quantization, dict):
                qtables = [list(quantization[key]) for key in sorted(quantization)]
                subsampling = JpegImagePlugin.get_sampling(source)
            normalized = ImageOps.exif_transpose(source)
            exif_object = normalized.getexif()
            exif_object.pop(274, None)
            exif = exif_object.tobytes() if exif_object else None
            pixels = np.asarray(normalized.convert("RGB"), dtype=np.uint8).copy()
    except (OSError, UnidentifiedImageError) as error:
        raise ImageIOError(f"cannot decode image: {path}") from error
    return LoadedImage(
        pixels_rgb=pixels,
        source_format=source_format,
        exif=exif,
        icc_profile=icc_profile if isinstance(icc_profile, bytes) else None,
        dpi=dpi,
        jpeg_qtables=qtables,
        jpeg_subsampling=subsampling,
    )


def allocate_output_path(source: Path) -> Path:
    """Choose a sibling output name without overwriting an existing result."""

    output_directory = source.parent / OUTPUT_DIRECTORY_NAME
    suffix = source.suffix.lower()
    candidate = output_directory / f"{source.stem}_clean{suffix}"
    index = 2
    while candidate.exists():
        candidate = output_directory / f"{source.stem}_clean_{index}{suffix}"
        index += 1
    return candidate


def _save_options(loaded: LoadedImage) -> dict[str, object]:
    options: dict[str, object] = {}
    if loaded.exif:
        options["exif"] = loaded.exif
    if loaded.icc_profile:
        options["icc_profile"] = loaded.icc_profile
    if loaded.dpi:
        options["dpi"] = loaded.dpi
    if loaded.source_format == "JPEG":
        if loaded.jpeg_qtables:
            options["qtables"] = loaded.jpeg_qtables
        else:
            options["quality"] = 95
        if loaded.jpeg_subsampling is not None:
            options["subsampling"] = loaded.jpeg_subsampling
    elif loaded.source_format == "PNG":
        options["compress_level"] = 6
    elif loaded.source_format in {"TIFF", "TIF"}:
        options["compression"] = "tiff_deflate"
    return options


def _verify_output(path: Path, expected_size: tuple[int, int]) -> None:
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            if image.size != expected_size:
                raise ImageIOError(
                    f"temporary output size {image.size} does not match {expected_size}"
                )
            image.convert("RGB").getpixel((0, 0))
    except (OSError, UnidentifiedImageError) as error:
        raise ImageIOError(f"temporary output validation failed: {path}") from error


def write_image_atomic(
    loaded: LoadedImage,
    pixels_rgb: NDArray[np.uint8],
    output: Path,
) -> Path:
    """Write beside the final target, verify, then rename without source access."""

    if pixels_rgb.dtype != np.uint8 or pixels_rgb.ndim != 3 or pixels_rgb.shape[2] != 3:
        raise ValueError("output pixels must be an HxWx3 uint8 RGB array")
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.parent / f".{output.stem}.{uuid4().hex}.tmp{output.suffix}"
    image_format = "JPEG" if loaded.source_format == "JPG" else loaded.source_format
    if image_format == "TIF":
        image_format = "TIFF"
    try:
        Image.fromarray(pixels_rgb, mode="RGB").save(
            temporary,
            format=image_format,
            **_save_options(loaded),
        )
        _verify_output(
            temporary,
            (int(pixels_rgb.shape[1]), int(pixels_rgb.shape[0])),
        )
        os.rename(temporary, output)
    except Exception as error:
        temporary.unlink(missing_ok=True)
        if isinstance(error, (FileExistsError, ImageIOError)):
            raise
        raise ImageIOError(f"failed to write output: {output}") from error
    return output
