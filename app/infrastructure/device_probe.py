"""Read-only device capability detection."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from importlib.util import find_spec


@dataclass(frozen=True, slots=True)
class DeviceInfo:
    gpu_name: str | None
    driver_version: str | None
    memory_mib: int | None
    onnx_providers: tuple[str, ...]


def _probe_nvidia() -> tuple[str | None, str | None, int | None]:
    command = [
        "nvidia-smi",
        "--query-gpu=name,driver_version,memory.total",
        "--format=csv,noheader,nounits",
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None, None, None

    first_line = completed.stdout.splitlines()[0] if completed.stdout.strip() else ""
    fields = [field.strip() for field in first_line.split(",")]
    if len(fields) != 3:
        return None, None, None
    try:
        memory_mib = int(fields[2])
    except ValueError:
        memory_mib = None
    return fields[0] or None, fields[1] or None, memory_mib


def _probe_onnx_providers() -> tuple[str, ...]:
    if find_spec("onnxruntime") is None:
        return ()
    command = [
        sys.executable,
        "-c",
        (
            "import json, onnxruntime as ort; "
            "print(json.dumps(ort.get_available_providers()))"
        ),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=True,
            text=True,
            timeout=10,
        )
        providers = json.loads(completed.stdout)
    except (json.JSONDecodeError, subprocess.SubprocessError):
        return ()
    return tuple(str(provider) for provider in providers)


def probe_device() -> DeviceInfo:
    gpu_name, driver_version, memory_mib = _probe_nvidia()
    return DeviceInfo(
        gpu_name=gpu_name,
        driver_version=driver_version,
        memory_mib=memory_mib,
        onnx_providers=_probe_onnx_providers(),
    )
