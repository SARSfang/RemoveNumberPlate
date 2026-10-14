"""Collect notices from the optional runtime without modifying standard notices."""
from pathlib import Path

from scripts import collect_licenses

HD_RUNTIME_DISTRIBUTIONS: tuple[str, ...] = (
    "torch", "numpy", "opencv-python-headless", "filelock", "fsspec", "jinja2",
    "MarkupSafe", "networkx", "sympy", "mpmath", "typing-extensions",
)


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    target = root / "dist" / "hd-component" / "third_party_licenses_hd"
    assert target.resolve().is_relative_to(root.resolve())
    collect_licenses.OUTPUT_DIR = target
    collect_licenses.RUNTIME_DISTRIBUTIONS = HD_RUNTIME_DISTRIBUTIONS
    return collect_licenses.main()


if __name__ == "__main__":
    raise SystemExit(main())
