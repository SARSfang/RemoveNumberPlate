"""Source-preserving real-photo comparison; legacy baseline comes from Git HEAD."""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import time
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

from app.cli import build_processor
from app.config import MODELS_DIR
from app.core.image_io import load_image
from app.core.mask_builder import DEFAULT_MARGIN_RATIO, PlateMaskPolicy, build_plate_mask
from app.core.repair_config import RepairConfig
from app.infrastructure.lama_inpainter import _context_bounds
from app.infrastructure.quality_inpainter import QualityInpainter


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, default=Path("output/hd-validation"))
    parser.add_argument("--skip-stress", action="store_true")
    parser.add_argument("--margin", type=float, default=DEFAULT_MARGIN_RATIO)
    args = parser.parse_args()
    folder = args.output
    folder.mkdir(parents=True, exist_ok=True)
    image = load_image(args.source).pixels_rgb
    processor = build_processor(0.6, repair_config=RepairConfig(quality="standard"))
    detections = processor._detector.detect(image)
    if not detections:
        raise RuntimeError("No plate detected; supply a confirmed manual mask instead")
    height, width = image.shape[:2]
    mask = build_plate_mask((int(height), int(width)), detections,
                            PlateMaskPolicy(args.margin))
    Image.fromarray(mask).save(folder / "mask.png")
    x1, y1, x2, y2 = _context_bounds(mask, 2)
    Image.fromarray(image[y1:y2, x1:x2]).save(folder / "original-crop.png")
    legacy_path = folder / "legacy_adapter.py"
    legacy_path.write_bytes(subprocess.run(
        ["git", "show", "HEAD:app/infrastructure/lama_inpainter.py"],
        capture_output=True, check=True,
    ).stdout)
    spec = importlib.util.spec_from_file_location("legacy_lama", legacy_path)
    assert spec is not None and spec.loader is not None
    legacy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(legacy)
    variants = [
        ("legacy", legacy.LamaInpainter(MODELS_DIR / "inpainting_lama_2025jan.onnx")),
        ("standard", QualityInpainter(MODELS_DIR, RepairConfig(
            quality="standard", texture_enabled=False))),
        ("high", QualityInpainter(MODELS_DIR, RepairConfig(
            quality="high", texture_enabled=False))),
        ("high-texture", QualityInpainter(MODELS_DIR, RepairConfig(quality="high"))),
    ]
    report: dict[str, object] = {"source": str(args.source), "size": list(image.shape[:2]),
                                "mask_margin": args.margin,
                                "detections": [asdict(d) for d in detections]}
    cards = []
    for name, inpainter in variants:
        started = time.perf_counter()
        output = inpainter.inpaint(image, mask)
        elapsed = time.perf_counter() - started
        outside_equal = bool(np.array_equal(output[mask == 0], image[mask == 0]))
        Image.fromarray(output).save(folder / f"{name}-full.png")
        crop = output[y1:y2, x1:x2]
        Image.fromarray(crop).save(folder / f"{name}-crop.png")
        # Same pixels, same display size; no resampling in comparison cards.
        card = Image.new("RGB", (crop.shape[1], crop.shape[0]+32), "white")
        card.paste(Image.fromarray(crop), (0, 32))
        ImageDraw.Draw(card).text((8, 8), name, fill="black")
        cards.append(card)
        report[name] = {"elapsed_seconds": round(elapsed, 3),
                        "outside_mask_equal": outside_equal,
                        "diagnostics": getattr(inpainter, "diagnostics", [])}
        print(name, report[name], flush=True)
        (folder / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                             encoding="utf-8")
    montage = Image.new("RGB", (sum(c.width for c in cards), max(c.height for c in cards)))
    offset = 0
    for card in cards:
        montage.paste(card, (offset, 0))
        offset += card.width
    montage.save(folder / "comparison.png")
    if args.skip_stress:
        return
    # Input shape stress tests do not serve as photographic quality evidence.
    hd = variants[2][1]._hd()
    stress = []
    for side in (1024, 1536, 2048):
        crop = cv2.resize(image[y1:y2, x1:x2], (side, side))
        selected = cv2.resize(mask[y1:y2, x1:x2], (side, side),
                              interpolation=cv2.INTER_NEAREST)
        started = time.perf_counter()
        out = hd.generate_crop(crop, selected, side)
        stress.append({"side": side, "elapsed_seconds": round(time.perf_counter()-started, 3),
                       "shape_valid": out.shape == crop.shape})
        report["shape_stress_only"] = stress
        (folder / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                             encoding="utf-8")
        print(stress[-1], flush=True)


if __name__ == "__main__":
    main()
