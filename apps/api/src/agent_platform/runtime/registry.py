from __future__ import annotations

from typing import Any

from agent_platform.domain.models import CapabilityDefinition
from agent_platform.plugins.base import CapabilityPlugin
from agent_platform.plugins.executors import HttpExecutor, McpExecutor, PlatformProxyPlugin
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
        self._package_diagnostics: list[dict[str, str]] = []
        self._loader = loader or PackageLoader.default()
        self.refresh_package_capabilities()

    # ------------------------------------------------------------------ refresh
    def refresh_package_capabilities(self) -> None:
        new: dict[str, CapabilityPlugin] = {}
        diagnostics: list[dict[str, str]] = []
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
                        plugin_meta=plugin_meta,
                        diagnostics=diagnostics,
                    )
                    if plugin is None:
                        continue
                    new[name] = plugin
        self._package_plugins = new
        self._package_diagnostics = diagnostics

    def _build_executor(
        self,
        *,
        executor_kind: str,
        capability: CapabilityDefinition,
        package_id: str,
        plugin_name: str,
        config_schema: dict[str, Any] | None,
        default_config: dict[str, Any],
        binding: dict[str, Any],
        plugin_meta: dict[str, Any],
        diagnostics: list[dict[str, str]],
    ) -> CapabilityPlugin | None:
        if executor_kind == "http":
            return HttpExecutor(
                capability,
                package_id=package_id,
                plugin_name=plugin_name,
                binding=binding,
                plugin_config_schema=config_schema,
                plugin_default_config=default_config,
            )
        if executor_kind == "platform":
            return self._build_platform_executor(
                capability=capability,
                package_id=package_id,
                plugin_name=plugin_name,
                plugin_meta=plugin_meta,
                diagnostics=diagnostics,
            )
        if executor_kind == "mcp":
            return McpExecutor(
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

    def _build_platform_executor(
        self,
        *,
        capability: CapabilityDefinition,
        package_id: str,
        plugin_name: str,
        plugin_meta: dict[str, Any],
        diagnostics: list[dict[str, str]],
    ) -> CapabilityPlugin | None:
        raw_ref = str(plugin_meta.get("platform_plugin") or "").strip()
        if not raw_ref:
            self._append_diagnostic(
                diagnostics,
                package_id=package_id,
                plugin_name=plugin_name,
                capability_name=capability.name,
                code="PLATFORM_PLUGIN_REQUIRED",
                message="executor=platform requires platform_plugin.",
            )
            return None
        target_name, version_range = self._parse_platform_plugin_ref(raw_ref)
        target_plugin = self._find_builtin_plugin(target_name)
        if target_plugin is None:
            self._append_diagnostic(
                diagnostics,
                package_id=package_id,
                plugin_name=plugin_name,
                capability_name=capability.name,
                code="PLATFORM_PLUGIN_NOT_FOUND",
                message=f"Platform plugin not found: {target_name}",
            )
            return None
        target_version = str(getattr(target_plugin, "plugin_version", "1.0.0"))
        if version_range and not self._version_satisfies(target_version, version_range):
            self._append_diagnostic(
                diagnostics,
                package_id=package_id,
                plugin_name=plugin_name,
                capability_name=capability.name,
                code="PLATFORM_PLUGIN_VERSION_MISMATCH",
                message=(
                    f"Platform plugin {target_name}@{target_version} "
                    f"does not satisfy {version_range}."
                ),
            )
            return None
        return PlatformProxyPlugin(
            capability,
            package_id=package_id,
            plugin_name=plugin_name,
            target_plugin=target_plugin,
            platform_plugin_ref=raw_ref,
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

    def list_diagnostics(self) -> list[dict[str, str]]:
        return [dict(item) for item in self._package_diagnostics]

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

    def _find_builtin_plugin(self, target_name: str) -> CapabilityPlugin | None:
        if target_name in self._builtin_plugins:
            return self._builtin_plugins[target_name]
        for plugin in self._builtin_plugins.values():
            if getattr(plugin, "plugin_name", None) == target_name:
                return plugin
            if plugin.__class__.__name__ == target_name:
                return plugin
        return None

    @staticmethod
    def _validate_payload(capability: CapabilityDefinition, payload: dict[str, Any]) -> None:
        required_fields = capability.input_schema.get("required", [])
        missing_fields = [
            field for field in required_fields if field not in payload or payload[field] in ("", None)
        ]
        if missing_fields:
            raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

    @staticmethod
    def _append_diagnostic(
        diagnostics: list[dict[str, str]],
        *,
        package_id: str,
        plugin_name: str,
        capability_name: str,
        code: str,
        message: str,
    ) -> None:
        diagnostics.append(
            {
                "package_id": package_id,
                "plugin_name": plugin_name,
                "capability_name": capability_name,
                "code": code,
                "message": message,
            }
        )

    @staticmethod
    def _parse_platform_plugin_ref(raw_ref: str) -> tuple[str, str]:
        if "@" not in raw_ref:
            return raw_ref, ""
        target_name, version_range = raw_ref.rsplit("@", 1)
        return target_name.strip(), version_range.strip()

    @staticmethod
    def _version_tuple(version: str) -> tuple[int, int, int]:
        parts = version.strip().lstrip("v").split(".")
        numbers: list[int] = []
        for part in parts[:3]:
            digits = "".join(char for char in part if char.isdigit())
            numbers.append(int(digits or "0"))
        while len(numbers) < 3:
            numbers.append(0)
        return tuple(numbers)  # type: ignore[return-value]

    @classmethod
    def _version_satisfies(cls, version: str, version_range: str) -> bool:
        target = cls._version_tuple(version)
        constraints = version_range.strip()
        if not constraints:
            return True
        if constraints.startswith("~"):
            base = cls._version_tuple(constraints[1:])
            upper = (base[0], base[1] + 1, 0)
            return target >= base and target < upper
        for constraint in constraints.split():
            if constraint.startswith(">="):
                if target < cls._version_tuple(constraint[2:]):
                    return False
                continue
            if constraint.startswith(">"):
                if target <= cls._version_tuple(constraint[1:]):
                    return False
                continue
            if constraint.startswith("<="):
                if target > cls._version_tuple(constraint[2:]):
                    return False
                continue
            if constraint.startswith("<"):
                if target >= cls._version_tuple(constraint[1:]):
                    return False
                continue
            if constraint[0].isdigit() and target != cls._version_tuple(constraint):
                return False
        return True
