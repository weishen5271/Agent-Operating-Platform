from __future__ import annotations

from typing import Any

from agent_platform.domain.models import CapabilityDefinition, SourceReference
from agent_platform.plugins.base import CapabilityPlugin


class StubPackagePlugin(CapabilityPlugin):
    """Stand-in executor for capabilities declared by an uploaded business package.

    Bundle uploads carry only the capability **contract** (input/output schema,
    risk level, required scope) — never executor code. Until a real platform
    plugin package is published for the same capability name, this stub keeps
    the planning / orchestration / audit chain runnable end-to-end by
    synthesising a fixture response shaped against ``output_schema``.
    """

    def __init__(
        self,
        capability: CapabilityDefinition,
        *,
        package_id: str,
        plugin_name: str,
    ) -> None:
        self.capability = capability
        self._package_id = package_id
        self._plugin_name = plugin_name
        self.config_schema = None
        self.auth_ref = None

    def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        fixture: dict[str, Any] = {
            "stub": True,
            "capability": self.capability.name,
            "package_id": self._package_id,
            "plugin": self._plugin_name,
            "echo_input": payload,
            "summary": (
                f"[stub] {self.capability.name} 由业务包 {self._package_id} "
                f"以契约形式注册；等待平台插件包接入真实 executor。"
            ),
            "sources": [
                SourceReference(
                    id=f"stub::{self._package_id}::{self._plugin_name}",
                    title=f"业务包 stub · {self._plugin_name}",
                    snippet="占位实现，仅返回结构化 fixture。",
                    source_type="plugin",
                )
            ],
        }
        # Synthesise plausible defaults for the schema-required output fields so
        # downstream skill steps can keep navigating the data flow.
        for required_field in self.capability.output_schema.get("required", []) or []:
            if required_field in fixture:
                continue
            fixture[required_field] = self._default_for_field(required_field)
        return fixture

    @staticmethod
    def _default_for_field(field_name: str) -> Any:
        plural_hints = ("s", "list", "items", "history", "alarms", "alternatives")
        if any(field_name.endswith(suffix) for suffix in plural_hints):
            return []
        if field_name.endswith("_id") or field_name.endswith("Id"):
            return f"stub-{field_name}"
        return None
