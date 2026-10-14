"""Desktop application entry point."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from app.desktop import launch, smoke
from app.infrastructure.webview2 import WEBVIEW2_DOWNLOAD_URL, detect_webview2_version


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="消除车牌")
    parser.add_argument("--smoke", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--verify-image", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--verify-repair", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--verify-mask", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--verify-output", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--repair-quality", choices=("auto", "standard", "high"),
                        default="auto", help=argparse.SUPPRESS)
    arguments = parser.parse_args(argv)
    if arguments.smoke:
        return smoke()
    if arguments.verify_repair is not None:
        import json

        import numpy as np
        from PIL import Image

        from app.cli import build_manual_processor
        from app.core.repair_config import RepairConfig

        if arguments.verify_mask is None or arguments.verify_output is None:
            parser.error("--verify-repair requires --verify-mask and --verify-output")
        with Image.open(arguments.verify_mask) as mask_image:
            mask = np.asarray(mask_image.convert("L"), dtype=np.uint8)
        processor = build_manual_processor(RepairConfig(quality=arguments.repair_quality))
        result = processor.render_to(arguments.verify_repair, mask, arguments.verify_output)
        report = {"status": result.status.value, "elapsed_seconds": result.elapsed_seconds,
                  "warnings": result.warnings,
                  "diagnostics": getattr(processor._inpainter, "diagnostics", [])}
        arguments.verify_output.with_suffix(".verification.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return 0
    if arguments.verify_image is not None:
        from app.cli import build_processor
        from app.domain.job import JobStatus

        result = build_processor(0.60).process(arguments.verify_image)
        return 0 if result.status is not JobStatus.FAILED else 2
    if detect_webview2_version() is None:
        raise RuntimeError(
            "未检测到 Microsoft Edge WebView2 Runtime。"
            f"请安装后重试：{WEBVIEW2_DOWNLOAD_URL}"
        )
    return launch()
