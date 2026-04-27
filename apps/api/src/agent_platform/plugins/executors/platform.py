from __future__ import annotations

from typing import Any

from agent_platform.domain.models import CapabilityDefinition
from agent_platform.plugins.base import CapabilityPlugin


class PlatformProxyPlugin(CapabilityPlugin):
    """Bundle-declared capability that delegates execution to a built-in plugin."""

    def __init__(
        self,
        capability: CapabilityDefinition,
        *,
        package_id: str,
        plugin_name: str,
        target_plugin: CapabilityPlugin,
        platform_plugin_ref: str,
    ) -> None:
        self.capability = capability
        self.package_id = package_id
        self.plugin_name = plugin_name
        self.target_plugin = target_plugin
        self.platform_plugin_ref = platform_plugin_ref
        self.config_schema = getattr(target_plugin, "config_schema", None)
        self.auth_ref = getattr(target_plugin, "auth_ref", None)

    def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.target_plugin.invoke(payload)

    def invoke_with_config(
        self,
        payload: dict[str, Any],
        *,
        tenant_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.target_plugin.invoke_with_config(payload, tenant_config=tenant_config)
