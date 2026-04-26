from __future__ import annotations

from typing import Any

from agent_platform.domain.models import CapabilityDefinition
from agent_platform.plugins.base import CapabilityPlugin
from agent_platform.plugins.hr import HRLeaveBalancePlugin
from agent_platform.plugins.knowledge import KnowledgePlugin
from agent_platform.plugins.wiki import WikiSearchPlugin
from agent_platform.plugins.workflow import ProcurementDraftPlugin


class CapabilityRegistry:
    def __init__(self) -> None:
        plugins: list[CapabilityPlugin] = [
            KnowledgePlugin(),
            WikiSearchPlugin(),
            HRLeaveBalancePlugin(),
            ProcurementDraftPlugin(),
        ]
        self._plugins = {plugin.capability.name: plugin for plugin in plugins}

    def list_capabilities(self) -> list[CapabilityDefinition]:
        return [plugin.capability for plugin in self._plugins.values()]

    def list_plugins(self) -> list[CapabilityPlugin]:
        return list(self._plugins.values())

    def get_plugin(self, plugin_name: str) -> CapabilityPlugin:
        return self._plugins[plugin_name]

    def get(self, capability_name: str) -> CapabilityDefinition:
        return self._plugins[capability_name].capability

    def invoke(self, capability_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        plugin = self._plugins[capability_name]
        self._validate_payload(plugin.capability, payload)
        return plugin.invoke(payload)

    @staticmethod
    def _validate_payload(capability: CapabilityDefinition, payload: dict[str, Any]) -> None:
        required_fields = capability.input_schema.get("required", [])
        missing_fields = [field for field in required_fields if field not in payload or payload[field] in ("", None)]
        if missing_fields:
            raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")
