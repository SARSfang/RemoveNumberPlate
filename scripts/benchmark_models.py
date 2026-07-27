"""Benchmark the pinned plate detector on a local image or directory."""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageOps

from app.config import AppPaths
from app.core.detector import Detector
from app.core.two_stage_detector import VehicleFirstPlateDetector
from app.infrastructure.paddle_plate_detector import PaddlePlateDetector
from app.infrastructure.paddle_vehicle_detector import PaddleVehicleDetector

SUPPORTED_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}


def discover_images(path: Path) -> list[Path]:
    if path.is_file():
        return [path] if path.suffix.lower() in SUPPORTED_SUFFIXES else []
    if not path.is_dir():
        return []
    return sorted(
        candidate
        for candidate in path.rglob("*")
        if candidate.is_file() and candidate.suffix.lower() in SUPPORTED_SUFFIXES
    )


def load_rgb(path: Path) -> NDArray[np.uint8]:
    with Image.open(path) as image:
        normalized = ImageOps.exif_transpose(image).convert("RGB")
        return np.asarray(normalized, dtype=np.uint8)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--cpu", action="store_true")
    parser.add_argument("--limit-side-len", type=int, default=960)
    parser.add_argument("--limit-type", choices=("max", "min"), default="max")
    parser.add_argument("--threshold", type=float, default=0.3)
    parser.add_argument("--box-threshold", type=float, default=0.6)
    parser.add_argument(
        "--two-stage",
        action="store_true",
        help="detect vehicles first with the pinned PP-YOLOE-S model",
    )
    parser.add_argument(
        "--crop",
        type=int,
        nargs=4,
        metavar=("X1", "Y1", "X2", "Y2"),
    )
    arguments = parser.parse_args()

    images = discover_images(arguments.input)
    if not images:
        parser.error("no supported images found")

    model_dir = AppPaths.default().models_dir / "ch_PP-OCRv3_det_infer"
    start = time.perf_counter()
    plate_detector = PaddlePlateDetector(
        model_dir,
        use_gpu=not arguments.cpu,
        limit_side_len=arguments.limit_side_len,
        limit_type=arguments.limit_type,
        threshold=arguments.threshold,
        box_threshold=arguments.box_threshold,
    )
    detector: Detector = plate_detector
    if arguments.two_stage:
        vehicle_model_dir = (
            AppPaths.default().models_dir / "PP-YOLOE-S_vehicle_infer"
        )
        detector = VehicleFirstPlateDetector(
            PaddleVehicleDetector(
                vehicle_model_dir,
                use_gpu=not arguments.cpu,
            ),
            plate_detector,
        )
    startup_seconds = time.perf_counter() - start

    rows: list[dict[str, object]] = []
    elapsed_values: list[float] = []
    for image_path in images:
        image = load_rgb(image_path)
        crop_offset = (0, 0)
        if arguments.crop is not None:
            x1, y1, x2, y2 = arguments.crop
            if not (0 <= x1 < x2 <= image.shape[1] and 0 <= y1 < y2 <= image.shape[0]):
                parser.error("crop must be inside the image")
            image = image[y1:y2, x1:x2]
            crop_offset = (x1, y1)
        start = time.perf_counter()
        detections = detector.detect(image)
        elapsed = time.perf_counter() - start
        elapsed_values.append(elapsed)
        rows.append(
            {
                "path": str(image_path),
                "width": int(image.shape[1]),
                "height": int(image.shape[0]),
                "elapsed_seconds": round(elapsed, 6),
                "detections": [
                    {
                        "confidence": round(detection.confidence, 6),
                        "box": [
                            round(detection.box.x1 + crop_offset[0], 2),
                            round(detection.box.y1 + crop_offset[1], 2),
                            round(detection.box.x2 + crop_offset[0], 2),
                            round(detection.box.y2 + crop_offset[1], 2),
                        ],
                    }
                    for detection in detections
                ],
            }
        )

    report = {
        "runtime": "paddle-gpu" if not arguments.cpu else "paddle-cpu",
        "pipeline": "vehicle-first" if arguments.two_stage else "plate-only",
        "startup_seconds": round(startup_seconds, 6),
        "image_count": len(rows),
        "median_seconds": round(statistics.median(elapsed_values), 6),
        "results": rows,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
