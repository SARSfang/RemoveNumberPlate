"""Benchmark a warm reusable processor over repeated isolated source copies."""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from app.cli import build_processor


def _gpu_memory_mib() -> int | None:
    try:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.used",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            check=True,
            text=True,
            timeout=3,
        )
        return max(int(line.strip()) for line in completed.stdout.splitlines() if line.strip())
    except (FileNotFoundError, ValueError, subprocess.SubprocessError):
        return None


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return ordered[index]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=10)
    arguments = parser.parse_args()
    if not arguments.input.is_file():
        parser.error("input image does not exist")
    if arguments.repeats < 2:
        parser.error("repeats must be at least 2")

    samples: list[int] = []
    stop_sampling = threading.Event()

    def sample_memory() -> None:
        while not stop_sampling.wait(0.15):
            value = _gpu_memory_mib()
            if value is not None:
                samples.append(value)

    sampler = threading.Thread(target=sample_memory, daemon=True)
    sampler.start()
    build_started = time.perf_counter()
    processor = build_processor(0.60)
    construction_seconds = time.perf_counter() - build_started
    elapsed_values: list[float] = []
    statuses: list[str] = []
    total_started = time.perf_counter()
    try:
        with tempfile.TemporaryDirectory(prefix="plate-remover-benchmark-") as directory:
            root = Path(directory)
            sources: list[Path] = []
            for index in range(arguments.repeats):
                source = root / f"sample_{index + 1:03d}{arguments.input.suffix.lower()}"
                shutil.copy2(arguments.input, source)
                sources.append(source)
            for source in sources:
                started = time.perf_counter()
                result = processor.process(source)
                elapsed_values.append(time.perf_counter() - started)
                statuses.append(result.status.value)
    finally:
        stop_sampling.set()
        sampler.join(5)
    total_seconds = time.perf_counter() - total_started
    warm_values = elapsed_values[1:]
    report = {
        "image_count": len(elapsed_values),
        "construction_seconds": round(construction_seconds, 4),
        "cold_first_seconds": round(elapsed_values[0], 4),
        "warm_p50_seconds": round(_percentile(warm_values, 0.50), 4),
        "warm_p95_seconds": round(_percentile(warm_values, 0.95), 4),
        "total_seconds": round(total_seconds, 4),
        "throughput_images_per_minute": round(len(elapsed_values) / total_seconds * 60, 2),
        "peak_gpu_memory_mib": max(samples) if samples else None,
        "statuses": statuses,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(status == "completed" for status in statuses) else 2


if __name__ == "__main__":
    raise SystemExit(main())
