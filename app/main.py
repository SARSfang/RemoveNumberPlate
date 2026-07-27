"""Desktop application entry point."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from app.desktop import launch, smoke


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="消除车牌")
    parser.add_argument("--smoke", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--verify-image", type=Path, help=argparse.SUPPRESS)
    arguments = parser.parse_args(argv)
    if arguments.smoke:
        return smoke()
    if arguments.verify_image is not None:
        from app.cli import build_processor
        from app.domain.job import JobStatus

        result = build_processor(0.60).process(arguments.verify_image)
        return 0 if result.status is not JobStatus.FAILED else 2
    return launch()
