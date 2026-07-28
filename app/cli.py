"""Developer CLI for the offline batch-processing core."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.config import AppPaths
from app.core.batch import BatchReport, process_batch, resume_batch
from app.core.job_store import JobStore
from app.core.mask_builder import DEFAULT_MARGIN_RATIO, PlateMaskPolicy
from app.core.pipeline import ImageProcessor, ManualMaskProcessor
from app.core.two_stage_detector import VehicleFirstPlateDetector
from app.domain.job import JobStatus
from app.infrastructure.lama_inpainter import LamaInpainter
from app.infrastructure.model_registry import load_manifest
from app.infrastructure.onnx_detectors import OnnxPlateDetector, OnnxVehicleDetector


def _verify_enabled_models(paths: AppPaths) -> None:
    failures: list[str] = []
    for artifact in load_manifest(paths.model_manifest):
        if artifact.enabled and not artifact.verify(paths.models_dir / artifact.filename):
            failures.append(artifact.model_id)
    if failures:
        raise RuntimeError(f"missing or invalid model artifacts: {', '.join(failures)}")


def build_processor(
    auto_confidence: float,
    mask_margin_ratio: float = DEFAULT_MARGIN_RATIO,
) -> ImageProcessor:
    paths = AppPaths.default()
    _verify_enabled_models(paths)
    detector = VehicleFirstPlateDetector(
        OnnxVehicleDetector(paths.models_dir / "ppyoloe_vehicle.onnx"),
        OnnxPlateDetector(
            paths.models_dir / "ppocrv3_plate.onnx",
            limit_side_len=736,
            limit_type="min",
        ),
    )
    inpainter = LamaInpainter(paths.models_dir / "inpainting_lama_2025jan.onnx")
    return ImageProcessor(
        detector,
        inpainter,
        auto_confidence=auto_confidence,
        mask_policy=PlateMaskPolicy(mask_margin_ratio),
    )


def build_manual_processor() -> ManualMaskProcessor:
    paths = AppPaths.default()
    _verify_enabled_models(paths)
    return ManualMaskProcessor(
        LamaInpainter(paths.models_dir / "inpainting_lama_2025jan.onnx")
    )


def report_as_mapping(report: BatchReport) -> dict[str, Any]:
    return {
        "total": len(report.items),
        "completed": report.count(JobStatus.COMPLETED),
        "review_required": report.count(JobStatus.REVIEW_REQUIRED),
        "no_plate": report.count(JobStatus.NO_PLATE),
        "failed": report.count(JobStatus.FAILED),
        "elapsed_seconds": round(report.elapsed_seconds, 6),
        "items": [
            {
                "source": str(item.source),
                "status": item.result.status.value,
                "output": str(item.result.output) if item.result.output else None,
                "elapsed_seconds": round(item.result.elapsed_seconds, 6),
                "detection_count": item.result.detection_count,
                "risks": [risk.value for risk in item.result.risks],
                "error": item.result.error,
            }
            for item in report.items
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="remove-number-plate")
    subparsers = parser.add_subparsers(dest="command", required=True)
    process_parser = subparsers.add_parser("process", help="process images or folders")
    process_parser.add_argument("inputs", type=Path, nargs="+")
    process_parser.add_argument("--confidence", type=float, default=0.60)
    resume_parser = subparsers.add_parser("resume", help="resume interrupted jobs")
    resume_parser.add_argument("--confidence", type=float, default=0.60)
    subparsers.add_parser("report", help="show persisted job counts")
    arguments = parser.parse_args(argv)

    paths = AppPaths.default()
    if arguments.command == "process":
        processor = build_processor(arguments.confidence)
        with JobStore(paths.job_database) as store:
            report = process_batch(arguments.inputs, processor, store)
        print(json.dumps(report_as_mapping(report), ensure_ascii=False, indent=2))
        if not report.items:
            return 1
        return 2 if report.count(JobStatus.FAILED) else 0
    if arguments.command == "resume":
        with JobStore(paths.job_database) as store:
            store.recover_interrupted()
            pending = store.list_jobs((JobStatus.QUEUED,))
            if not pending:
                print(json.dumps({"resumed": 0}, ensure_ascii=False, indent=2))
                return 0
            processor = build_processor(arguments.confidence)
            report = resume_batch(pending, processor, store)
        print(json.dumps(report_as_mapping(report), ensure_ascii=False, indent=2))
        return 2 if report.count(JobStatus.FAILED) else 0
    if arguments.command == "report":
        with JobStore(paths.job_database) as store:
            value = {"counts": store.counts()}
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
