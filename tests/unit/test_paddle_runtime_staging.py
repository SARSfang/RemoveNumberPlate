from pathlib import Path

import pytest

from app.infrastructure.paddle_plate_detector import (
    PaddleDetectorError,
    _contains_non_ascii,
    stage_paddle_model,
)


def test_ascii_model_path_does_not_copy(tmp_path: Path) -> None:
    if _contains_non_ascii(tmp_path):
        pytest.skip("pytest base path contains non-ASCII characters")

    assert stage_paddle_model(tmp_path) == tmp_path


def test_non_ascii_runtime_root_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "model"
    source.mkdir()
    monkeypatch.setattr(
        "app.infrastructure.paddle_plate_detector._contains_non_ascii",
        lambda path: True,
    )

    with pytest.raises(PaddleDetectorError, match="ASCII"):
        stage_paddle_model(source, tmp_path / "模型")
