from __future__ import annotations

from typing import Any

from agent_platform.domain.models import CapabilityDefinition
from agent_platform.plugins.base import CapabilityPlugin
from agent_platform.plugins.executors import HttpExecutor
from agent_platform.plugins.hr import HRLeaveBalancePlugin
from agent_platform.plugins.knowledge import KnowledgePlugin
from agent_platform.plugins.stub import StubPackagePlugin
from agent_platform.plugins.wiki import WikiSearchPlugin
from agent_platform.plugins.workflow import ProcurementDraftPlugin
from agent_platform.runtime.package_loader import PackageLoader


class CapabilityRegistry:
    """Registry of capabilities + their executor plugins.

    Built-in plugins ship with the platform image and always win on name
    collision (we never let an uploaded bundle shadow a real executor). Bundle
    plugins declared as ``executor: "stub"`` are loaded lazily via
    :meth:`refresh_package_capabilities` so end-to-end planning, governance and
    audit chains stay runnable before a real platform plugin is published.
    """

    def __init__(self, *, loader: PackageLoader | None = None) -> None:
        builtins: list[CapabilityPlugin] = [
            KnowledgePlugin(),
            WikiSearchPlugin(),
            HRLeaveBalancePlugin(),
            ProcurementDraftPlugin(),
        ]
        self._builtin_plugins: dict[str, CapabilityPlugin] = {
            plugin.capability.name: plugin for plugin in builtins
        }
        self._package_plugins: dict[str, CapabilityPlugin] = {}
        self._loader = loader or PackageLoader.default()
        self.refresh_package_capabilities()

    # ------------------------------------------------------------------ refresh
    def refresh_package_capabilities(self) -> None:
        new: dict[str, CapabilityPlugin] = {}
        for package in self._loader.list_packages():
            package_id = str(package.get("package_id", ""))
            if not package_id:
                continue
            for plugin_meta in package.get("plugins", []) or []:
                if not isinstance(plugin_meta, dict):
                    continue
                executor_kind = str(plugin_meta.get("executor") or "stub").lower()
                plugin_name = str(plugin_meta.get("name") or "").strip()
                if not plugin_name:
                    continue
                config_schema = plugin_meta.get("config_schema") or None
                default_config = plugin_meta.get("default_config") or {}
                for raw_cap in plugin_meta.get("capabilities", []) or []:
                    if not isinstance(raw_cap, dict):
                        continue
                    name = str(raw_cap.get("name") or "").strip()
                    if not name or name in self._builtin_plugins:
                        # Real platform-level executor wins; skip overlay.
                        continue
                    capability = CapabilityDefinition(
                        name=name,
                        description=str(raw_cap.get("description", "")),
                        risk_level=str(raw_cap.get("risk_level", "low")),
                        side_effect_level=str(raw_cap.get("side_effect_level", "read")),
                        required_scope=str(raw_cap.get("required_scope", "")),
                        input_schema=dict(raw_cap.get("input_schema") or {}),
                        output_schema=dict(raw_cap.get("output_schema") or {}),
                        enabled=bool(raw_cap.get("enabled", True)),
                        source="package",
                        package_id=package_id,
                    )
                    plugin = self._build_executor(
                        executor_kind=executor_kind,
                        capability=capability,
                        package_id=package_id,
                        plugin_name=plugin_name,
                        config_schema=config_schema,
                        default_config=default_config,
                        binding=raw_cap.get("binding") or {},
                    )
                    new[name] = plugin
        self._package_plugins = new

    @staticmethod
    def _build_executor(
        *,
        executor_kind: str,
        capability: CapabilityDefinition,
        package_id: str,
        plugin_name: str,
        config_schema: dict[str, Any] | None,
        default_config: dict[str, Any],
        binding: dict[str, Any],
    ) -> CapabilityPlugin:
        if executor_kind == "http":
            return HttpExecutor(
                capability,
                package_id=package_id,
                plugin_name=plugin_name,
                binding=binding,
                plugin_config_schema=config_schema,
                plugin_default_config=default_config,
            )
        # Default: stub fixture executor.
        return StubPackagePlugin(
            capability,
            package_id=package_id,
            plugin_name=plugin_name,
        )

    # ------------------------------------------------------------------ lookups
    @property
    def _plugins(self) -> dict[str, CapabilityPlugin]:
        merged: dict[str, CapabilityPlugin] = dict(self._package_plugins)
        merged.update(self._builtin_plugins)
        return merged

    def list_capabilities(self) -> list[CapabilityDefinition]:
        return [plugin.capability for plugin in self._plugins.values()]

    def list_plugins(self) -> list[CapabilityPlugin]:
        return list(self._plugins.values())

    def get_plugin(self, plugin_name: str) -> CapabilityPlugin:
        plugins = self._plugins
        if plugin_name in plugins:
            return plugins[plugin_name]
        # Bundle plugins host multiple capabilities under one plugin_name; fall
        # back to a name-based lookup so the admin UI can configure them.
        for plugin in plugins.values():
            if getattr(plugin, "plugin_name", None) == plugin_name:
                return plugin
        raise KeyError(plugin_name)

    def get(self, capability_name: str) -> CapabilityDefinition:
        return self._plugins[capability_name].capability

    def invoke(
        self,
        capability_name: str,
        payload: dict[str, Any],
        *,
        tenant_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        plugin = self._plugins[capability_name]
        self._validate_payload(plugin.capability, payload)
        return plugin.invoke_with_config(payload, tenant_config=tenant_config)

    def get_plugin_name_for_capability(self, capability_name: str) -> str:
        plugin = self._plugins.get(capability_name)
        if plugin is None:
            return capability_name
        # HttpExecutor / StubPackagePlugin both expose ``plugin_name``;
        # built-in plugins fall back to the capability name (legacy mapping).
        return getattr(plugin, "plugin_name", capability_name)

    @staticmethod
    def _validate_payload(capability: CapabilityDefinition, payload: dict[str, Any]) -> None:
        required_fields = capability.input_schema.get("required", [])
        missing_fields = [
            field for field in required_fields if field not in payload or payload[field] in ("", None)
        ]
        if missing_fields:
            raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")
