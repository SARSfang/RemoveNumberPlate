"""Run automatic vehicle detection, full-plate masking, and LaMa inpainting."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from app.config import AppPaths
from app.core.mask_builder import build_plate_mask
from app.core.two_stage_detector import VehicleFirstPlateDetector
from app.infrastructure.lama_inpainter import LamaInpainter
from app.infrastructure.paddle_plate_detector import PaddlePlateDetector
from app.infrastructure.paddle_vehicle_detector import PaddleVehicleDetector


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()

    with Image.open(arguments.input) as source:
        image = np.asarray(ImageOps.exif_transpose(source).convert("RGB"), dtype=np.uint8)
    paths = AppPaths.default()
    start = time.perf_counter()
    detector = VehicleFirstPlateDetector(
        PaddleVehicleDetector(
            paths.models_dir / "PP-YOLOE-S_vehicle_infer",
            use_gpu=True,
        ),
        PaddlePlateDetector(
            paths.models_dir / "ch_PP-OCRv3_det_infer",
            use_gpu=True,
            limit_side_len=736,
            limit_type="min",
        ),
    )
    inpainter = LamaInpainter(paths.models_dir / "inpainting_lama_2025jan.onnx")
    startup_seconds = time.perf_counter() - start

    start = time.perf_counter()
    detections = detector.detect(image)
    mask = build_plate_mask(
        (int(image.shape[0]), int(image.shape[1])),
        detections,
    )
    result = inpainter.inpaint(image, mask)
    processing_seconds = time.perf_counter() - start

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(result, mode="RGB").save(arguments.output, quality=95)
    report = {
        "startup_seconds": round(startup_seconds, 6),
        "processing_seconds": round(processing_seconds, 6),
        "detections": [
            {
                "confidence": round(value.confidence, 6),
                "text_box": [
                    round(value.box.x1, 2),
                    round(value.box.y1, 2),
                    round(value.box.x2, 2),
                    round(value.box.y2, 2),
                ],
            }
            for value in detections
        ],
        "mask_pixels": int(np.count_nonzero(mask)),
        "output": str(arguments.output),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
