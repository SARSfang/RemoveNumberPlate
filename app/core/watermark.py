"""Watermark renderer: overlay text watermarks onto images using Pillow."""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

LOGGER = logging.getLogger("remove_number_plate.watermark")

# 9 宫格位置常量
_POSITIONS = frozenset(
    {
        "top-left",
        "top-center",
        "top-right",
        "center-left",
        "center",
        "center-right",
        "bottom-left",
        "bottom-center",
        "bottom-right",
    }
)

# Windows 系统字体路径
_FONT_PATHS = (
    "C:\\Windows\\Fonts\\arial.ttf",
    "C:\\Windows\\Fonts\\msyh.ttc",
)


@dataclass(frozen=True, slots=True)
class WatermarkConfig:
    """Watermark configuration (text or image)."""

    enabled: bool = False
    type: str = "text"
    text: str = ""
    font_size: int = 24
    color: str = "#FFFFFF"
    opacity: float = 0.7
    position: str = "bottom-right"
    margin: int = 16
    image_path: str = ""
    image_scale: float = 0.2

    def __post_init__(self) -> None:
        if self.type not in ("text", "image"):
            raise ValueError(f"unsupported watermark type: {self.type}")
        if self.font_size <= 0:
            raise ValueError("font_size must be positive")
        if not 0.0 <= self.opacity <= 1.0:
            raise ValueError("opacity must be between 0.0 and 1.0")
        if self.position not in _POSITIONS:
            raise ValueError(f"unsupported position: {self.position}")
        if self.margin < 0:
            raise ValueError("margin must be non-negative")
        if not 0.05 <= self.image_scale <= 1.0:
            raise ValueError("image_scale must be between 0.05 and 1.0")


class WatermarkRenderer:
    """Render text or image watermarks onto images using Pillow."""

    def __init__(self, config: WatermarkConfig) -> None:
        self._config = config

    def _has_content(self) -> bool:
        if self._config.type == "image":
            return bool(self._config.image_path.strip())
        return bool(self._config.text.strip())

    def render(self, image_path: Path, output_path: Path) -> Path:
        """Apply watermark to image, save atomically. Returns output_path.

        If watermark is disabled or has no content, the image is copied
        unchanged to output_path.
        """

        if not self._config.enabled or not self._has_content():
            _copy_atomic(image_path, output_path)
            return output_path

        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = (
            output_path.parent / f".{output_path.stem}.{uuid.uuid4().hex}.tmp"
        )
        try:
            with Image.open(image_path) as base:
                base.load()
                format_name = base.format or image_path.suffix.lstrip(".").upper()
                watermarked = self._draw_watermark(base)
                save_options = _build_save_options(base)
                if format_name.upper() == "JPG":
                    format_name = "JPEG"
                watermarked.save(temporary, format=format_name, **save_options)
            os.replace(temporary, output_path)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return output_path

    def _draw_watermark(self, base: Image.Image) -> Image.Image:
        """Draw the configured watermark onto a copy of base image."""

        if self._config.type == "image" and self._config.image_path.strip():
            return self._draw_image_watermark(base)
        return self._draw_text_watermark(base)

    def _draw_text_watermark(self, base: Image.Image) -> Image.Image:
        """Draw text watermark onto a copy of base image."""

        rgba_base = base.convert("RGBA")
        overlay = Image.new("RGBA", rgba_base.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        font = self._load_font(self._config.font_size)
        text = self._config.text
        color_rgb = _parse_color(self._config.color)
        alpha = int(255 * self._config.opacity)
        text_color = (color_rgb[0], color_rgb[1], color_rgb[2], alpha)

        # 测量文本大小（Pillow 10+ 使用 textbbox）
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = int(bbox[2] - bbox[0])
        text_height = int(bbox[3] - bbox[1])

        x, y = _compute_position(
            self._config.position,
            rgba_base.size[0],
            rgba_base.size[1],
            text_width,
            text_height,
            self._config.margin,
        )

        draw.text((x, y), text, font=font, fill=text_color)
        return Image.alpha_composite(rgba_base, overlay).convert(
            _output_mode(base)
        )

    def _draw_image_watermark(self, base: Image.Image) -> Image.Image:
        """Draw image watermark onto a copy of base image.

        The watermark image is scaled relative to the shorter side of the
        base image, then positioned and alpha-composited.
        """

        rgba_base = base.convert("RGBA")
        try:
            watermark = Image.open(self._config.image_path).convert("RGBA")
            watermark.load()
        except OSError as error:
            LOGGER.warning(
                "watermark image not found %s: %s",
                self._config.image_path,
                error,
            )
            return rgba_base.convert(_output_mode(base))

        target = max(1, int(min(rgba_base.size) * self._config.image_scale))
        ratio = target / max(1, watermark.width)
        new_size = (
            target,
            max(1, int(watermark.height * ratio)),
        )
        watermark = watermark.resize(new_size, Image.Resampling.LANCZOS)

        if self._config.opacity < 1.0:
            alpha_channel = watermark.split()[3]
            alpha_channel = alpha_channel.point(
                lambda pixel: int(pixel * self._config.opacity)
            )
            watermark.putalpha(alpha_channel)

        x, y = _compute_position(
            self._config.position,
            rgba_base.size[0],
            rgba_base.size[1],
            watermark.width,
            watermark.height,
            self._config.margin,
        )
        rgba_base.paste(watermark, (x, y), watermark)
        return rgba_base.convert(_output_mode(base))

    def _load_font(
        self, size: int
    ) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        """Try system fonts first, fall back to Pillow's default."""

        for font_path in _FONT_PATHS:
            try:
                return ImageFont.truetype(font_path, size)
            except OSError:
                continue
        return ImageFont.load_default()


def _compute_position(
    position: str,
    canvas_width: int,
    canvas_height: int,
    text_width: int,
    text_height: int,
    margin: int,
) -> tuple[int, int]:
    """Compute (x, y) for top-left of text box based on 9-grid position."""

    if position.startswith("top"):
        y = margin
    elif position.startswith("center"):
        y = (canvas_height - text_height) // 2
    else:  # bottom
        y = canvas_height - text_height - margin

    if position.endswith("left"):
        x = margin
    elif position.endswith("center"):
        x = (canvas_width - text_width) // 2
    else:  # right
        x = canvas_width - text_width - margin

    return x, y


def _parse_color(hex_color: str) -> tuple[int, int, int]:
    """Parse #RRGGBB hex color to (r, g, b)."""

    color = hex_color.lstrip("#")
    if len(color) != 6:
        LOGGER.warning("invalid color %s, defaulting to white", hex_color)
        return (255, 255, 255)
    try:
        return (int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16))
    except ValueError:
        LOGGER.warning("invalid color %s, defaulting to white", hex_color)
        return (255, 255, 255)


def _output_mode(base: Image.Image) -> str:
    """Preserve the original image mode after watermark compositing."""

    mode = base.mode
    if mode in ("RGB", "L", "CMYK"):
        return mode
    return "RGB"


def _build_save_options(base: Image.Image) -> dict[str, object]:
    """Carry over EXIF / ICC profile from the source image."""

    options: dict[str, object] = {}
    exif = base.info.get("exif")
    if exif:
        options["exif"] = exif
    icc_profile = base.info.get("icc_profile")
    if icc_profile:
        options["icc_profile"] = icc_profile
    dpi = base.info.get("dpi")
    if isinstance(dpi, tuple) and len(dpi) == 2:
        options["dpi"] = dpi
    return options


def _copy_atomic(source: Path, destination: Path) -> None:
    """Copy file atomically (temp file → rename)."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = (
        destination.parent / f".{destination.stem}.{uuid.uuid4().hex}.tmp"
    )
    try:
        import shutil

        shutil.copy2(source, temporary)
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
