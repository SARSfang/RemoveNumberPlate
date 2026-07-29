"""Post-processor: coordinate naming, watermark, and EXIF after removal."""

from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path

from app.core.exif_writer import ExifWriter
from app.core.naming_template import NamingContext, NamingTemplate
from app.core.watermark import WatermarkRenderer
from app.settings import PostProcessConfig

LOGGER = logging.getLogger("remove_number_plate.post_processor")


class PostProcessor:
    """Coordinate post-processing steps after plate removal.

    Steps execute in order: rename → watermark → EXIF.
    Each step is independent; failure in one doesn't block others.
    Final output path is returned for database storage.
    """

    def __init__(self, config: PostProcessConfig) -> None:
        self._config = config
        self._watermark_renderer = WatermarkRenderer(config.watermark)
        self._exif_writer = ExifWriter(config.exif)

    def process(
        self,
        source_path: Path,  # 原片路径
        removal_output: Path,  # 车牌消除后的输出路径
        sequence: int,  # 批次内序号
        client: str = "",  # 客户名（来自项目预设）
    ) -> Path:
        """Execute post-processing. Returns final output path.

        If post-processing is disabled, returns removal_output unchanged.
        On any error, logs warning and returns removal_output (original
        elimination result is always preserved).
        """
        if not self._config.enabled:
            return removal_output

        try:
            # Step 1: Compute output path via naming template
            template = NamingTemplate(self._config.naming_template)
            context = NamingContext(
                original_stem=source_path.stem,
                extension=source_path.suffix,
                sequence=sequence,
                client=client,
                shot_date=_extract_shot_date(source_path),
            )
            filename = template.render(context)
            final_output = template.resolve_conflict(
                removal_output.parent, filename
            )

            # Step 2: Copy removal output to final path (start from elimination result)
            shutil.copy2(removal_output, final_output)

            # Step 3: Apply watermark
            if self._config.watermark.enabled and self._config.watermark.text.strip():
                temp = (
                    final_output.parent
                    / f".{final_output.stem}.wm.tmp{final_output.suffix}"
                )
                self._watermark_renderer.render(final_output, temp)
                final_output.unlink()
                temp.rename(final_output)

            # Step 4: Apply EXIF
            if self._config.exif.enabled:
                temp = (
                    final_output.parent
                    / f".{final_output.stem}.exif.tmp{final_output.suffix}"
                )
                self._exif_writer.write(final_output, temp)
                final_output.unlink()
                temp.rename(final_output)

            return final_output
        except Exception as error:
            LOGGER.warning(
                "post-processing failed for %s: %s; keeping removal output",
                removal_output,
                error,
            )
            return removal_output


def _extract_shot_date(source: Path) -> str:
    """Extract shot date as YYYYMMDD from EXIF, fall back to mtime."""
    try:
        from PIL import Image

        with Image.open(source) as img:
            exif = img.getexif()
            # DateTimeOriginal = 36867, DateTimeDigitized = 36868
            date_str = exif.get(36867) or exif.get(36868) or ""
            if date_str:
                # Format: "2024:01:15 10:30:00"
                return str(date_str)[:10].replace(":", "")
    except Exception:
        pass
    return time.strftime("%Y%m%d", time.localtime(source.stat().st_mtime))
