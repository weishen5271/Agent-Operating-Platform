from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from agent_platform.domain.models import CapabilityDefinition


class CapabilityPlugin(ABC):
    capability: CapabilityDefinition
    config_schema: dict[str, Any] | None = None
    auth_ref: str | None = None

    @abstractmethod
    def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError
