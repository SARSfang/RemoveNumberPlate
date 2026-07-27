"""Desktop application entry point.

The M2 batch core is available through ``python -m app.cli``. The Qt window is
the next milestone; this entry point currently performs a safe environment
check.
"""

from __future__ import annotations

from app.config import AppPaths
from app.infrastructure.device_probe import probe_device


def main() -> int:
    paths = AppPaths.default()
    device = probe_device()
    print("RemoveNumberPlate batch core is ready.")
    print("Run: python -m app.cli process <image-or-folder>")
    print(f"Model manifest: {paths.model_manifest}")
    print(f"GPU: {device.gpu_name or 'not detected'}")
    return 0
