from __future__ import annotations

from typing import Any

import pytest

from agent_platform.runtime.registry import CapabilityRegistry


class StaticPackageLoader:
    def __init__(self, packages: list[dict[str, Any]]) -> None:
        self._packages = packages

    def list_packages(self) -> list[dict[str, Any]]:
        return self._packages


def platform_package(*, platform_plugin: str) -> dict[str, Any]:
    return {
        "package_id": "pkg.platform_ref",
        "name": "Platform Reference Package",
        "version": "1.0.0",
        "owner": "test",
        "status": "test",
        "domain": "common",
        "source_kind": "bundle",
        "plugins": [
            {
                "name": "platform.knowledge.proxy",
                "executor": "platform",
                "platform_plugin": platform_plugin,
                "capabilities": [
                    {
                        "name": "bundle.knowledge.search",
                        "description": "Bundle contract delegated to platform knowledge search",
                        "risk_level": "low",
                        "side_effect_level": "read",
                        "required_scope": "knowledge:read",
                        "input_schema": {"required": ["query"]},
                        "output_schema": {"required": ["summary", "matches"]},
                    }
                ],
            }
        ],
    }


def test_platform_executor_delegates_to_builtin_plugin() -> None:
    registry = CapabilityRegistry(loader=StaticPackageLoader([platform_package(platform_plugin="knowledge.search@>=1.0.0 <2.0.0")]))

    capability = registry.get("bundle.knowledge.search")
    result = registry.invoke("bundle.knowledge.search", {"query": "bundle"})

    assert capability.source == "package"
    assert capability.package_id == "pkg.platform_ref"
    assert "summary" in result
    assert "matches" in result
    assert registry.list_diagnostics() == []


def test_platform_executor_skips_missing_builtin_plugin_with_diagnostic() -> None:
    registry = CapabilityRegistry(loader=StaticPackageLoader([platform_package(platform_plugin="missing.platform@1.0.0")]))

    with pytest.raises(KeyError):
        registry.get("bundle.knowledge.search")

    diagnostics = registry.list_diagnostics()
    assert diagnostics == [
        {
            "package_id": "pkg.platform_ref",
            "plugin_name": "platform.knowledge.proxy",
            "capability_name": "bundle.knowledge.search",
            "code": "PLATFORM_PLUGIN_NOT_FOUND",
            "message": "Platform plugin not found: missing.platform",
        }
    ]


def test_platform_executor_skips_version_mismatch_with_diagnostic() -> None:
    registry = CapabilityRegistry(loader=StaticPackageLoader([platform_package(platform_plugin="knowledge.search@>=2.0.0")]))

    with pytest.raises(KeyError):
        registry.get("bundle.knowledge.search")

    diagnostics = registry.list_diagnostics()
    assert diagnostics[0]["code"] == "PLATFORM_PLUGIN_VERSION_MISMATCH"
    assert diagnostics[0]["package_id"] == "pkg.platform_ref"
    assert "knowledge.search@1.0.0" in diagnostics[0]["message"]
