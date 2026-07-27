from pathlib import Path

from scripts.benchmark_models import discover_images


def test_discover_images_filters_and_sorts(tmp_path: Path) -> None:
    (tmp_path / "b.JPG").write_bytes(b"")
    (tmp_path / "a.png").write_bytes(b"")
    (tmp_path / "note.txt").write_text("ignored", encoding="utf-8")

    images = discover_images(tmp_path)

    assert [image.name for image in images] == ["a.png", "b.JPG"]
