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

    def invoke_with_config(
        self,
        payload: dict[str, Any],
        *,
        tenant_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Optional hook for executors that need tenant-scoped config.

        Default forwards to :meth:`invoke` so existing built-in plugins keep
        working unchanged. ``HttpExecutor`` and ``McpExecutor`` override this
        to read endpoint / auth_ref / secrets from ``tenant_config``.
        """
        return self.invoke(payload)
