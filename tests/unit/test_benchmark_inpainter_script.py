from pathlib import Path

from scripts import benchmark_inpainter


def test_benchmark_inpainter_module_exposes_main() -> None:
    assert callable(benchmark_inpainter.main)
    assert Path(benchmark_inpainter.__file__).name == "benchmark_inpainter.py"
