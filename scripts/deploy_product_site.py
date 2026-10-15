"""Server-side transactional deployment of the independent product page only.

Usage: python3 deploy_product_site.py <archive.tar.gz> <numeric release stamp>
The archive contains manifest.json and product/ files. No other site is touched.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tarfile
from pathlib import Path, PurePosixPath

TARGET = Path("/var/www/fangdian-products/remove-number-plate")
STAGE_ROOT = Path("/tmp")
RECORD_ROOT = Path("/opt/sitewide-visual-backups")
PAGES = {"index.html", "404.html", "styles.css", "site.js"}
ALLOWED = PAGES | {
    "LICENSE.txt", "THIRD_PARTY_NOTICES.txt", "assets/logo.png",
    "assets/original.webp", "assets/legacy.webp", "assets/high.webp",
    "assets/high-full.webp",
    "assets/pfd32132-result-960.webp", "assets/pfd32132-result-1920.webp",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_baseline(expected: dict[str, str]) -> None:
    if set(expected) != {"index.html", "styles.css", "site.js"}:
        raise ValueError("Expected baseline must identify all three primary files")
    for name, sha in expected.items():
        if digest(TARGET / name) != sha:
            raise ValueError("Production changed since review: " + name)


def main() -> None:
    archive, stamp = sys.argv[1:]
    if not stamp.isascii() or not stamp.isdigit() or len(stamp) > 20:
        raise ValueError("Invalid release stamp")
    if TARGET.is_symlink() or not TARGET.is_dir():
        raise ValueError("Unexpected production target")
    if any(p.is_symlink() for p in TARGET.rglob("*")):
        raise ValueError("Unexpected symlink in production")
    stage = STAGE_ROOT / ("rnp-product-" + stamp)
    candidate = TARGET.with_name(TARGET.name + ".candidate-" + stamp)
    previous = TARGET.with_name(TARGET.name + ".before-" + stamp)
    failed = TARGET.with_name(TARGET.name + ".failed-" + stamp)
    record_dir = RECORD_ROOT / ("rnp-product-" + stamp)
    if any(p.exists() or p.is_symlink() for p in (stage, candidate, previous, failed, record_dir)):
        raise ValueError("Release paths already exist")
    stage.mkdir()
    with tarfile.open(archive) as tar:
        members = tar.getmembers()
        names = [m.name for m in members]
        if len(set(names)) != len(names):
            raise ValueError("Duplicate archive members")
        for member in members:
            member_path = PurePosixPath(member.name)
            if (
                not member.isfile() or member_path.is_absolute() or ".." in member_path.parts
                or member.name not in {"manifest.json"} | {"product/" + n for n in ALLOWED}
            ):
                raise ValueError("Unexpected archive member: " + member.name)
        tar.extractall(stage)
    manifest = json.loads((stage / "manifest.json").read_text())
    files: dict[str, str] = manifest["files"]
    expected: dict[str, str] = manifest["expected"]
    if set(files) != ALLOWED or set(names) != {"manifest.json"} | {"product/" + n for n in files}:
        raise ValueError("Manifest does not match the complete product file list")
    for name, sha in files.items():
        if digest(stage / "product" / name) != sha:
            raise ValueError("Package hash mismatch: " + name)
    verify_baseline(expected)
    shutil.copytree(TARGET, candidate)
    shutil.copytree(stage / "product", candidate, dirs_exist_ok=True)
    for name, sha in files.items():
        if digest(candidate / name) != sha:
            raise ValueError("Candidate hash mismatch: " + name)
    record_dir.mkdir(parents=True)
    verify_baseline(expected)
    os.rename(TARGET, previous)
    switched = False
    try:
        os.rename(candidate, TARGET)
        switched = True
        for name, sha in files.items():
            if digest(TARGET / name) != sha:
                raise ValueError("Published hash mismatch: " + name)
        record = dict(manifest, stamp=stamp, backup=str(previous), status="deployed")
        (record_dir / "release.json").write_text(json.dumps(record, indent=2))
    except Exception:
        if switched:
            os.rename(TARGET, failed)
        os.rename(previous, TARGET)
        raise
    print(json.dumps({"status": "deployed", "files": len(files), "backup": str(previous),
                      "record": str(record_dir / "release.json")}))


if __name__ == "__main__":
    main()
