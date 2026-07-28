"""Rebuild or download every enabled model from its pinned source."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from typing import Any

BUFFER_SIZE = 1024 * 1024
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(BUFFER_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def verify(path: Path, expected: str) -> bool:
    return path.is_file() and sha256(path) == expected.lower()


def safe_extract_tar(archive: Path, destination: Path) -> None:
    root = destination.resolve()
    with tarfile.open(archive, "r:*") as bundle:
        for member in bundle.getmembers():
            target = (destination / member.name).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError(f"unsafe archive member: {member.name}")
            if member.issym() or member.islnk():
                raise RuntimeError(f"archive links are not allowed: {member.name}")
        bundle.extractall(destination)


def download(url: str, destination: Path) -> None:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "RemoveNumberPlate-ModelBuilder/0.2"},
    )
    with (
        urllib.request.urlopen(request, timeout=120) as response,
        destination.open("wb") as stream,
    ):
        shutil.copyfileobj(response, stream, BUFFER_SIZE)


def acquire_artifact(
    artifact: dict[str, Any],
    work_dir: Path,
    source_cache: Path | None,
) -> Path:
    filename = str(artifact["filename"])
    expected = str(artifact["sha256"])
    if source_cache is not None:
        cached = source_cache / filename
        if verify(cached, expected):
            return cached
    destination = work_dir / filename
    download(str(artifact["source_url"]), destination)
    if not verify(destination, expected):
        raise RuntimeError(f"downloaded artifact failed SHA-256: {filename}")
    return destination


def find_unique(root: Path, filename: str) -> Path:
    matches = [path for path in root.rglob(filename) if path.is_file()]
    if len(matches) != 1:
        raise RuntimeError(f"expected one {filename}, found {len(matches)}")
    return matches[0]


def convert_paddle(
    source_archive: Path,
    build: dict[str, Any],
    destination: Path,
    work_dir: Path,
) -> None:
    paddle = importlib.import_module("paddle")
    paddle2onnx = importlib.import_module("paddle2onnx")

    paddle_version = str(paddle.__version__)
    paddle2onnx_version = str(paddle2onnx.__version__)
    if paddle_version != str(build["paddle_version"]):
        raise RuntimeError(
            f"expected paddle {build['paddle_version']}, found {paddle_version}"
        )
    if paddle2onnx_version != str(build["paddle2onnx_version"]):
        raise RuntimeError(
            "expected paddle2onnx "
            f"{build['paddle2onnx_version']}, found {paddle2onnx_version}"
        )
    extracted = work_dir / "source"
    extracted.mkdir()
    safe_extract_tar(source_archive, extracted)
    model = find_unique(extracted, str(build["model_filename"]))
    params = find_unique(extracted, str(build["params_filename"]))
    export = paddle2onnx.export
    export(
        model_filename=str(model),
        params_filename=str(params),
        save_file=str(destination),
        opset_version=int(build["opset_version"]),
        auto_upgrade_opset=True,
        dist_prim_all=False,
        verbose=False,
        enable_onnx_checker=True,
        enable_experimental_op=True,
        enable_optimize=True,
        custom_op_info=None,
        deploy_backend="onnxruntime",
        calibration_file="",
        external_file="",
        export_fp16_model=False,
        optimize_tool="polygraphy",
    )


def build_models(
    manifest_path: Path,
    output_dir: Path,
    source_cache: Path | None,
    *,
    force: bool,
) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifacts = {item["model_id"]: item for item in manifest["models"]}
    output_dir.mkdir(parents=True, exist_ok=True)
    for artifact in artifacts.values():
        if not artifact.get("enabled"):
            continue
        destination = output_dir / str(artifact["filename"])
        expected = str(artifact["sha256"])
        if not force and verify(destination, expected):
            print(f"verified existing model: {destination.name}")
            continue
        build = artifact.get("build")
        if not isinstance(build, dict):
            raise RuntimeError(f"missing build recipe: {artifact['model_id']}")
        with tempfile.TemporaryDirectory(prefix="plate-model-") as temporary:
            work_dir = Path(temporary)
            candidate = work_dir / destination.name
            if build.get("kind") == "download":
                source = acquire_artifact(artifact, work_dir, source_cache)
                shutil.copyfile(source, candidate)
            elif build.get("kind") == "paddle2onnx":
                source_artifact = artifacts[str(build["source_model_id"])]
                source = acquire_artifact(source_artifact, work_dir, source_cache)
                convert_paddle(source, build, candidate, work_dir)
            else:
                raise RuntimeError(f"unsupported build kind: {build.get('kind')}")
            if not verify(candidate, expected):
                raise RuntimeError(
                    f"reproducibility check failed for {destination.name}: "
                    f"expected {expected}, got {sha256(candidate)}"
                )
            staged = destination.with_suffix(destination.suffix + ".part")
            shutil.copyfile(candidate, staged)
            staged.replace(destination)
            print(f"built and verified model: {destination.name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        type=Path,
        default=PROJECT_ROOT / "models" / "manifest.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "models",
    )
    parser.add_argument("--source-cache", type=Path)
    parser.add_argument("--force", action="store_true")
    arguments = parser.parse_args()
    build_models(
        arguments.manifest,
        arguments.output_dir,
        arguments.source_cache,
        force=arguments.force,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
