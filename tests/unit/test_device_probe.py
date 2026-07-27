from app.infrastructure.device_probe import probe_device


def test_device_probe_never_requires_optional_runtime() -> None:
    device = probe_device()

    assert isinstance(device.onnx_providers, tuple)
