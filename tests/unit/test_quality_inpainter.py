from pathlib import Path

import numpy as np
import pytest

from app.core.repair_config import RepairConfig
from app.core.texture import enhance_texture
from app.infrastructure.migan_inpainter import InpainterError
from app.infrastructure.quality_inpainter import QualityInpainter
from app.settings import SettingsStore, UserSettings


class FakeModel:
    def generate_crop(self, image, mask, *args):
        return np.full_like(image, 80)


def adapter(config):
    item = QualityInpainter.__new__(QualityInpainter)
    item.config = config
    item._standard = FakeModel()
    item._high = FakeModel()
    return item


def test_texture_defaults_and_legacy_settings(tmp_path: Path):
    path = tmp_path / "settings.json"
    path.write_text('{"preset":"quality"}', encoding="utf-8")
    assert SettingsStore(path).load().repair_config == RepairConfig()
    assert RepairConfig().texture_enabled is True
    settings = UserSettings(repair_config=RepairConfig("high", False, 0.7, 2048))
    SettingsStore(path).save(settings)
    assert SettingsStore(path).load() == settings


@pytest.mark.parametrize("value", [
    {"texture_enabled": "false"}, {"texture_strength": float("nan")},
    {"hd_max_side": True}, {"quality": "invalid"}, {"unknown": 1},
])
def test_invalid_repair_options_rejected(value):
    with pytest.raises(ValueError):
        RepairConfig.parse(value)


def test_auto_fallback_is_visible_and_high_mode_never_silently_falls_back():
    image = np.zeros((800, 800, 3), dtype=np.uint8)
    mask = np.zeros((800, 800), dtype=np.uint8)
    mask[250:550, 250:550] = 255
    class Missing:
        def generate_crop(self, *args):
            raise InpainterError("missing model")
    item = adapter(RepairConfig(texture_enabled=False))
    item._high = Missing()
    out = item.inpaint(image, mask)
    assert item.warnings and item.diagnostics[0]["fallback"] == "missing model"
    np.testing.assert_array_equal(out[mask == 0], image[mask == 0])
    item.config = RepairConfig(quality="high")
    with pytest.raises(InpainterError, match="missing model"):
        item.inpaint(image, mask)


def test_overlapping_contexts_preserve_previous_repair():
    image = np.zeros((200, 300, 3), dtype=np.uint8)
    mask = np.zeros((200, 300), dtype=np.uint8)
    mask[70:110, 80:120] = 255
    mask[70:110, 130:170] = 255
    out = adapter(RepairConfig("standard", False)).inpaint(image, mask)
    assert out[90, 100, 0] == 80 and out[90, 150, 0] == 80
    np.testing.assert_array_equal(out[mask == 0], image[mask == 0])


def test_texture_skips_flat_source_and_excludes_other_plates():
    image = np.full((120, 120, 3), 100, dtype=np.uint8)
    mask = np.zeros((120, 120), dtype=np.uint8)
    mask[40:60, 40:60] = 255
    out, reason = enhance_texture(image, image.copy(), mask, mask, 0.25)
    assert reason == "no_matching_texture"
    np.testing.assert_array_equal(out, image)
    rng = np.random.default_rng(8)
    image = np.clip(image.astype(float) + rng.normal(0, 1.5, image.shape), 0, 255).astype(np.uint8)
    blocked = np.full_like(mask, 255)
    _, reason = enhance_texture(image, image.copy(), mask, blocked, 0.25)
    assert reason == "no_matching_texture"


def test_texture_transfers_real_detail_only_inside_mask():
    rng = np.random.default_rng(8)
    image = np.clip(100 + rng.normal(0, 1.5, (120, 120, 3)), 0, 255).astype(np.uint8)
    generated = np.full_like(image, 100)
    mask = np.zeros((120, 120), dtype=np.uint8)
    mask[40:70, 40:70] = 255
    out, reason = enhance_texture(image, generated, mask, mask, 0.5)
    assert reason == "applied"
    assert np.any(out[mask > 0] != generated[mask > 0])
    np.testing.assert_array_equal(out[mask == 0], generated[mask == 0])
