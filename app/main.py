"""Desktop application entry point.

The Qt window is intentionally deferred until the M1 model gate is passed.
For now this entry point performs a safe environment check and exits cleanly.
"""

from __future__ import annotations

from app.config import AppPaths
from app.infrastructure.device_probe import probe_device


def main() -> int:
    paths = AppPaths.default()
    device = probe_device()
    print("RemoveNumberPlate foundation is ready.")
    print(f"Model manifest: {paths.model_manifest}")
    print(f"GPU: {device.gpu_name or 'not detected'}")
    return 0
