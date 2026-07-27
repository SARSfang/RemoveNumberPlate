"""Benchmark the pinned MI-GAN inpainter with a rectangular remove mask."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from app.config import AppPaths
from app.core.inpainter import Inpainter
from app.infrastructure.lama_inpainter import LamaInpainter
from app.infrastructure.migan_inpainter import MiganInpainter


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument(
        "--box",
        type=int,
        nargs=4,
        required=True,
        metavar=("X1", "Y1", "X2", "Y2"),
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--model", choices=("migan", "lama"), default="migan")
    arguments = parser.parse_args()

    with Image.open(arguments.input) as source:
        image = np.asarray(ImageOps.exif_transpose(source).convert("RGB"), dtype=np.uint8)
    x1, y1, x2, y2 = arguments.box
    if not (0 <= x1 < x2 <= image.shape[1] and 0 <= y1 < y2 <= image.shape[0]):
        parser.error("box must be inside the image")
    mask = np.zeros(image.shape[:2], dtype=np.uint8)
    mask[y1:y2, x1:x2] = 255

    start = time.perf_counter()
    paths = AppPaths.default()
    inpainter: Inpainter
    if arguments.model == "lama":
        inpainter = LamaInpainter(
            paths.models_dir / "inpainting_lama_2025jan.onnx",
        )
    else:
        inpainter = MiganInpainter(
            paths.models_dir / "migan_pipeline_v2.onnx",
            use_gpu=False,
        )
    startup_seconds = time.perf_counter() - start
    start = time.perf_counter()
    result = inpainter.inpaint(image, mask)
    elapsed_seconds = time.perf_counter() - start

    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(result, mode="RGB").save(arguments.output, quality=95)

    report = {
        "runtime": f"onnxruntime-cpu-{arguments.model}",
        "startup_seconds": round(startup_seconds, 6),
        "elapsed_seconds": round(elapsed_seconds, 6),
        "width": int(image.shape[1]),
        "height": int(image.shape[0]),
        "box": [x1, y1, x2, y2],
        "output": str(arguments.output) if arguments.output else None,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
