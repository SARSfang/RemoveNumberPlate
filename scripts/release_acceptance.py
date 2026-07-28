"""Fast, deterministic checks for a Windows release candidate."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from app.config import AppPaths
from app.version import __version__
from scripts.verify_models import build_report

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    executable = PROJECT_ROOT / "dist" / "消除车牌" / "消除车牌.exe"
    installer = (
        PROJECT_ROOT
        / "dist"
        / "installer"
        / f"消除车牌-Setup-v{__version__}-win64.exe"
    )
    require(executable.is_file(), f"missing executable: {executable}")
    require(installer.is_file(), f"missing installer: {installer}")
    require(installer.stat().st_size > 50 * 1024 * 1024, "installer is unexpectedly small")
    digest = hashlib.sha256(installer.read_bytes()).hexdigest()
    (installer.parent / "SHA256SUMS.txt").write_text(
        f"{digest}  {installer.name}\n",
        encoding="utf-8",
    )

    paths = AppPaths.default()
    model_report = build_report(paths.model_manifest, paths.models_dir)
    enabled_models = [item for item in model_report["models"] if item["enabled"]]
    require(
        bool(enabled_models) and all(item["verified"] for item in enabled_models),
        "model verification failed",
    )

    smoke = subprocess.run(
        [str(executable), "--smoke"],
        timeout=30,
        check=False,
    )
    require(smoke.returncode == 0, f"desktop smoke failed: {smoke.returncode}")
    print(
        json.dumps(
            {
                "version": __version__,
                "desktop_smoke": "passed",
                "installer_bytes": installer.stat().st_size,
                "installer_sha256": digest,
                "models": model_report["models"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
