"""Copy the reviewed product page into MyWeb without replacing existing work."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path


def main() -> None:
    source = Path(__file__).resolve().parents[1] / "product-site"
    destination = Path(r"E:\MyWeb\products\remove-number-plate")
    if destination.is_symlink():
        raise RuntimeError("Product destination must not be a symlink")
    # README.md is development documentation and must not be published.
    excluded = {"README.md"}
    files = [path for path in source.rglob("*") if path.is_file() and path.name not in excluded]
    # Existing differing files require deliberate review; unrelated files survive.
    for path in files:
        target = destination / path.relative_to(source)
        if target.exists() and target.read_bytes() != path.read_bytes():
            raise RuntimeError(f"Existing file differs: {target}")
    for path in files:
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        if (
            hashlib.sha256(target.read_bytes()).digest()
            != hashlib.sha256(path.read_bytes()).digest()
        ):
            raise RuntimeError(f"Copy verification failed: {target}")
    print(f"Copied and verified {len(files)} files: {destination}")


if __name__ == "__main__":
    main()
