"""EXIF metadata writer using piexif, preserving existing data."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from shutil import copy2
from typing import Any
from uuid import uuid4

import piexif
from PIL import Image

LOGGER = logging.getLogger("remove_number_plate.exif_writer")

_SUPPORTED_FORMATS = frozenset({"JPEG", "TIFF", "TIF"})


@dataclass(frozen=True, slots=True)
class ExifConfig:
    """Configuration for EXIF metadata writing."""

    enabled: bool = False
    artist: str = ""
    copyright: str = ""
    description: str = ""


class ExifWriter:
    """Write EXIF metadata to images using piexif, preserving existing data."""

    def __init__(self, config: ExifConfig) -> None:
        self._config = config

    def _has_fields(self) -> bool:
        return bool(
            self._config.artist
            or self._config.copyright
            or self._config.description
        )

    def write(self, image_path: Path, output_path: Path) -> Path:
        """Read image, merge EXIF, write atomically. Returns output_path."""
        if not self._config.enabled or not self._has_fields():
            output_path.parent.mkdir(parents=True, exist_ok=True)
            copy2(image_path, output_path)
            return output_path

        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = (
            output_path.parent / f".{output_path.stem}.{uuid4().hex}.tmp{output_path.suffix}"
        )

        try:
            with Image.open(image_path) as img:
                format_name = (img.format or image_path.suffix.lstrip(".")).upper()
                if format_name not in _SUPPORTED_FORMATS:
                    copy2(image_path, output_path)
                    return output_path

                existing_exif = img.info.get("exif")
                exif_dict: dict[str, Any] = (
                    piexif.load(existing_exif)
                    if existing_exif
                    else {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
                )

                if self._config.artist:
                    exif_dict["0th"][piexif.ImageIFD.Artist] = self._config.artist.encode(
                        "utf-8"
                    )
                if self._config.copyright:
                    exif_dict["0th"][piexif.ImageIFD.Copyright] = self._config.copyright.encode(
                        "utf-8"
                    )
                if self._config.description:
                    exif_dict["0th"][piexif.ImageIFD.ImageDescription] = (
                        self._config.description.encode("utf-8")
                    )

                exif_bytes = piexif.dump(exif_dict)

                save_kwargs: dict[str, Any] = {"exif": exif_bytes}
                icc_profile = img.info.get("icc_profile")
                if isinstance(icc_profile, bytes):
                    save_kwargs["icc_profile"] = icc_profile

                save_format = "TIFF" if format_name == "TIF" else format_name
                img.save(temporary, format=save_format, **save_kwargs)

            os.replace(temporary, output_path)
            return output_path
        except Exception as error:
            LOGGER.warning(
                "EXIF write failed for %s, falling back to copy: %s",
                image_path,
                error,
            )
            temporary.unlink(missing_ok=True)
            if output_path.exists():
                output_path.unlink(missing_ok=True)
            copy2(image_path, output_path)
            return output_path
