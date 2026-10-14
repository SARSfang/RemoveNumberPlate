"""Shared, persistent repair options for automatic and manual workflows."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class RepairConfig:
    quality: str = "auto"
    texture_enabled: bool = True
    texture_strength: float = 0.25
    hd_max_side: int = 1536

    def __post_init__(self) -> None:
        if not isinstance(self.quality, str) or self.quality not in {"auto", "standard", "high"}:
            raise ValueError("未知的修复质量模式")
        if not isinstance(self.texture_enabled, bool):
            raise ValueError("纹理开关必须是布尔值")
        if (isinstance(self.texture_strength, bool)
                or not isinstance(self.texture_strength, (int, float))
                or not isfinite(self.texture_strength)
                or not 0 <= self.texture_strength <= 1):
            raise ValueError("纹理强度必须在 0 到 1 之间")
        if (isinstance(self.hd_max_side, bool) or not isinstance(self.hd_max_side, int)
                or self.hd_max_side not in {1024, 1536, 2048}):
            raise ValueError("高清裁剪上限必须为 1024、1536 或 2048")

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def parse(cls, value: object) -> RepairConfig:
        if value is None:
            return cls()
        if not isinstance(value, dict):
            raise ValueError("修复设置无效")
        unknown = set(value) - {"quality", "texture_enabled", "texture_strength", "hd_max_side"}
        if unknown:
            raise ValueError("修复设置含未知字段")
        return cls(**value)
