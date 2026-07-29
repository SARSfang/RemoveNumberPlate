"""Unit tests for NamingTemplate."""

from __future__ import annotations

from pathlib import Path

from app.core.naming_template import NamingContext, NamingTemplate


def _make_context(
    *,
    original_stem: str = "photo",
    extension: str = ".jpg",
    sequence: int = 1,
    client: str = "client_a",
    shot_date: str = "20260729",
) -> NamingContext:
    return NamingContext(
        original_stem=original_stem,
        extension=extension,
        sequence=sequence,
        client=client,
        shot_date=shot_date,
    )


def test_empty_template_uses_default() -> None:
    template = NamingTemplate("")
    context = _make_context(original_stem="IMG_001", extension=".jpg")
    assert template.render(context) == "IMG_001_clean.jpg"


def test_simple_template_render() -> None:
    template = NamingTemplate("{original}_clean{ext}")
    context = _make_context(original_stem="DSC0001", extension=".png")
    assert template.render(context) == "DSC0001_clean.png"


def test_sequence_padding() -> None:
    template = NamingTemplate("{seq:03}_{original}{ext}")
    context = _make_context(original_stem="photo", extension=".jpg", sequence=5)
    assert template.render(context) == "005_photo.jpg"


def test_client_placeholder_empty() -> None:
    template = NamingTemplate("{client}__{seq}")
    context = _make_context(client="", sequence=1)
    # Empty client -> empty string; double underscore preserved (not compressed)
    assert template.render(context) == "__1"


def test_date_placeholder() -> None:
    template = NamingTemplate("{date}_{original}{ext}")
    context = _make_context(original_stem="IMG_001", extension=".jpg", shot_date="20260115")
    assert template.render(context) == "20260115_IMG_001.jpg"


def test_illegal_characters_replaced() -> None:
    template = NamingTemplate("{original}{ext}")
    context = _make_context(original_stem="IMG:file*name?", extension=".jpg")
    # : * ? replaced with _
    assert template.render(context) == "IMG_file_name_.jpg"


def test_all_spaces_falls_back_to_default() -> None:
    template = NamingTemplate(" {client} ")
    context = _make_context(client="", original_stem="photo", extension=".jpg")
    # Renders to spaces -> falls back to default
    assert template.render(context) == "photo_clean.jpg"


def test_chinese_characters_preserved() -> None:
    template = NamingTemplate("{original}_clean{ext}")
    context = _make_context(original_stem="车牌照片", extension=".jpg")
    assert template.render(context) == "车牌照片_clean.jpg"


def test_resolve_conflict_no_collision(tmp_path: Path) -> None:
    template = NamingTemplate("{original}{ext}")
    result = template.resolve_conflict(tmp_path, "output.jpg")
    assert result == tmp_path / "output.jpg"


def test_resolve_conflict_increments(tmp_path: Path) -> None:
    template = NamingTemplate("{original}{ext}")
    (tmp_path / "output.jpg").touch()
    result = template.resolve_conflict(tmp_path, "output.jpg")
    assert result == tmp_path / "output_2.jpg"


def test_resolve_conflict_multiple_collisions(tmp_path: Path) -> None:
    template = NamingTemplate("{original}{ext}")
    (tmp_path / "output.jpg").touch()
    (tmp_path / "output_2.jpg").touch()
    (tmp_path / "output_3.jpg").touch()
    result = template.resolve_conflict(tmp_path, "output.jpg")
    assert result == tmp_path / "output_4.jpg"
