from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SUPPORTED_DATA_INPUT_MODES = {"platform_pull", "host_context", "mixed"}


@dataclass(slots=True)
class DataInput:
    """一次 AI Action 的数据输入来源声明。"""

    mode: str = "platform_pull"
    context: dict[str, Any] = field(default_factory=dict)

    def validate(self, allowed_modes: list[str]) -> None:
        """严格校验输入模式，避免未声明的 host_context 被悄悄接受。"""

        if self.mode not in SUPPORTED_DATA_INPUT_MODES:
            raise ValueError("Unsupported data input mode")
        if self.mode not in allowed_modes:
            raise ValueError("Data input mode is not allowed by action")
