from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from agent_platform.domain.models import CapabilityDefinition


class CapabilityPlugin(ABC):
    capability: CapabilityDefinition

    @abstractmethod
    def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

