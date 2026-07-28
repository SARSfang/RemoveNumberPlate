"""Bounded, read-only previews for persisted desktop jobs."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from enum import StrEnum
from io import BytesIO
from pathlib import Path

from PIL import Image

from app.core.image_io import ImageIOError, load_image
from app.core.job_store import StoredJob

MAIN_PREVIEW_BOUNDS = (1800, 1200)
MAIN_PREVIEW_QUALITY = 88
THUMBNAIL_BOUNDS = (320, 220)
THUMBNAIL_QUALITY = 72


class PreviewKind(StrEnum):
    ORIGINAL = "original"
    RESULT = "result"


class PreviewUnavailableReason(StrEnum):
    UNKNOWN_JOB = "unknown_job"
    SOURCE_MISSING = "source_missing"
    OUTPUT_NOT_READY = "output_not_ready"
    OUTPUT_MISSING = "output_missing"
    DECODE_FAILED = "decode_failed"
    INVALID_VARIANT = "invalid_variant"


_MESSAGES = {
    PreviewUnavailableReason.UNKNOWN_JOB: "找不到这个任务。",
    PreviewUnavailableReason.SOURCE_MISSING: "原照片已移动或删除。",
    PreviewUnavailableReason.OUTPUT_NOT_READY: "处理结果尚未生成。",
    PreviewUnavailableReason.OUTPUT_MISSING: "处理结果已移动或删除。",
    PreviewUnavailableReason.DECODE_FAILED: "无法读取这张照片的预览。",
    PreviewUnavailableReason.INVALID_VARIANT: "不支持的预览类型。",
}


@dataclass(frozen=True, slots=True)
class JobPreview:
    available: bool
    variant: str
    image: str = ""
    width: int = 0
    height: int = 0
    preview_width: int = 0
    preview_height: int = 0
    reason: PreviewUnavailableReason | None = None
    message: str = ""

    @classmethod
    def unavailable(
        cls,
        variant: str,
        reason: PreviewUnavailableReason,
    ) -> JobPreview:
        return cls(
            available=False,
            variant=variant,
            reason=reason,
            message=_MESSAGES[reason],
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "image": self.image,
            "width": self.width,
            "height": self.height,
            "preview_width": self.preview_width,
            "preview_height": self.preview_height,
            "variant": self.variant,
            "reason": self.reason.value if self.reason is not None else "",
            "message": self.message,
        }


def encode_preview(
    path: Path,
    *,
    variant: PreviewKind,
    bounds: tuple[int, int],
    quality: int,
) -> JobPreview:
    """Decode once, bound the pixels, and return an in-memory JPEG data URL."""

    if not path.is_file():
        reason = (
            PreviewUnavailableReason.SOURCE_MISSING
            if variant is PreviewKind.ORIGINAL
            else PreviewUnavailableReason.OUTPUT_MISSING
        )
        return JobPreview.unavailable(variant.value, reason)
    try:
        loaded = load_image(path)
    except ImageIOError:
        return JobPreview.unavailable(
            variant.value,
            PreviewUnavailableReason.DECODE_FAILED,
        )
    original_height, original_width = loaded.pixels_rgb.shape[:2]
    preview = Image.fromarray(loaded.pixels_rgb, mode="RGB")
    preview.thumbnail(bounds, Image.Resampling.LANCZOS)
    buffer = BytesIO()
    preview.save(buffer, format="JPEG", quality=quality, optimize=True)
    data_url = "data:image/jpeg;base64," + base64.b64encode(
        buffer.getvalue()
    ).decode("ascii")
    return JobPreview(
        available=True,
        variant=variant.value,
        image=data_url,
        width=int(original_width),
        height=int(original_height),
        preview_width=preview.width,
        preview_height=preview.height,
    )


def build_job_preview(
    job: StoredJob,
    kind: PreviewKind,
    *,
    bounds: tuple[int, int] = MAIN_PREVIEW_BOUNDS,
    quality: int = MAIN_PREVIEW_QUALITY,
) -> JobPreview:
    """Resolve a persisted job to an original or result preview."""

    if kind is PreviewKind.ORIGINAL:
        return encode_preview(
            job.source,
            variant=kind,
            bounds=bounds,
            quality=quality,
        )
    if job.output is None:
        return JobPreview.unavailable(
            kind.value,
            PreviewUnavailableReason.OUTPUT_NOT_READY,
        )
    return encode_preview(
        job.output,
        variant=kind,
        bounds=bounds,
        quality=quality,
    )
