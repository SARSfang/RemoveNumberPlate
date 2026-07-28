"""Collect installed runtime license files for binary redistribution."""

from __future__ import annotations

import importlib.metadata as metadata
import json
import re
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import cast

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "packaging" / "third_party_licenses"
RUNTIME_DISTRIBUTIONS = (
    "numpy",
    "onnxruntime",
    "opencv-python-headless",
    "Pillow",
    "piexif",
    "platformdirs",
    "pyclipper",
    "pywebview",
    "shapely",
)


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")


def main() -> int:
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, object]] = []
    for distribution_name in RUNTIME_DISTRIBUTIONS:
        distribution = metadata.distribution(distribution_name)
        package_name = distribution.metadata["Name"] or distribution_name
        copied: list[str] = []
        for relative in distribution.metadata.get_all("License-File", []):
            candidates = [
                file
                for file in (distribution.files or ())
                if str(file).replace("\\", "/").endswith(f"/{relative}")
            ]
            if not candidates:
                continue
            source = Path(str(distribution.locate_file(candidates[0])))
            if not source.is_file():
                continue
            destination_name = (
                f"{safe_name(package_name)}-{distribution.version}-"
                f"{safe_name(source.name)}"
            )
            shutil.copyfile(source, OUTPUT_DIR / destination_name)
            copied.append(destination_name)
        if not copied:
            fallback_files = [
                file
                for file in (distribution.files or ())
                if Path(str(file)).name.lower().startswith(("license", "copying"))
            ]
            for ordinal, file in enumerate(fallback_files, start=1):
                source = Path(str(distribution.locate_file(file)))
                if not source.is_file():
                    continue
                destination_name = (
                    f"{safe_name(package_name)}-{distribution.version}-"
                    f"{ordinal}-{safe_name(source.name)}"
                )
                shutil.copyfile(source, OUTPUT_DIR / destination_name)
                copied.append(destination_name)
        metadata_values = cast(Mapping[str, str], distribution.metadata)
        entries.append(
            {
                "name": package_name,
                "version": distribution.version,
                "license_expression": metadata_values.get("License-Expression"),
                "license": metadata_values.get("License"),
                "license_files": copied,
                "homepage": metadata_values.get("Project-URL"),
            }
        )
    (OUTPUT_DIR / "manifest.json").write_text(
        json.dumps(entries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Collected licenses for {len(entries)} runtime distributions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
