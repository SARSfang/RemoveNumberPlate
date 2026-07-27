"""Windows bootstrap helpers for the optional Paddle reference runtime."""

from __future__ import annotations

import os
import site
from pathlib import Path

_DLL_HANDLES: list[object] = []


def configure_nvidia_dll_search_path() -> tuple[Path, ...]:
    """Register NVIDIA wheel DLL directories without changing global PATH.

    PaddlePaddle 3.3 installs CUDA 13 runtime wheels under ``site-packages``
    on Windows, but those directories are not automatically visible to the
    Windows DLL loader in every launch environment.
    """

    if os.name != "nt" or not hasattr(os, "add_dll_directory"):
        return ()

    registered: list[Path] = []
    roots = [Path(value) for value in site.getsitepackages()]
    for root in roots:
        candidates = (
            root / "nvidia" / "cu13" / "bin" / "x86_64",
            root / "nvidia" / "cudnn" / "bin",
        )
        for candidate in candidates:
            if candidate.is_dir() and candidate not in registered:
                handle = os.add_dll_directory(str(candidate))
                _DLL_HANDLES.append(handle)
                registered.append(candidate)
    if registered:
        existing_path = os.environ.get("PATH", "")
        prefixes = [str(path) for path in registered]
        os.environ["PATH"] = os.pathsep.join([*prefixes, existing_path])
    return tuple(registered)
