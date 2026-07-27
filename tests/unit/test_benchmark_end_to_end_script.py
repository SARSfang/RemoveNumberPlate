from scripts import benchmark_end_to_end


def test_benchmark_end_to_end_module_exposes_main() -> None:
    assert callable(benchmark_end_to_end.main)
