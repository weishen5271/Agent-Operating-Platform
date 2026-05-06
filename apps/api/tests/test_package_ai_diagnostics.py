from __future__ import annotations

import asyncio
from pathlib import Path

from agent_platform.domain.models import UserContext
from agent_platform.runtime.chat_service import ChatService
from agent_platform.runtime.package_loader import PackageLoader
from agent_platform.runtime.registry import CapabilityRegistry
from agent_platform.runtime.skill_registry import SkillRegistry, ToolRegistry


class FakeUsers:
    async def get(self, tenant_id: str, user_id: str) -> UserContext:
        return UserContext(
            user_id=user_id,
            tenant_id=tenant_id,
            role="platform_admin",
            scopes=["admin:read"],
        )


class EmptyPluginConfigRepository:
    async def get(self, tenant_id: str, plugin_name: str) -> None:
        return None


def test_package_detail_returns_ai_action_dependency_diagnostics(monkeypatch) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    loader = PackageLoader(
        catalog_dir=repo_root / "packages" / "catalog",
        installed_dir=repo_root / "example" / "bundles",
    )
    monkeypatch.setattr(PackageLoader, "default", classmethod(lambda cls: loader))
    service = ChatService(
        registry=CapabilityRegistry(loader=loader),
        skills=SkillRegistry(loader=loader),
        tools=ToolRegistry(),
        conversations=object(),
        traces=object(),
        tenants=object(),
        tool_overrides=object(),
        output_guard_rules=object(),
        plugin_configs=EmptyPluginConfigRepository(),
        releases=object(),
        users=FakeUsers(),
        drafts=object(),
        security_events=object(),
        knowledge_sources=object(),
        knowledge_bases=object(),
        wiki_service=object(),
        llm_config=object(),
        llm_client=object(),
    )

    detail = asyncio.run(
        service.get_package_detail(
            package_id="industry.mfg_maintenance",
            tenant_id="tenant-a",
            user_id="admin",
        )
    )

    assert detail["business_objects"][0]["type"] == "equipment"
    diagnostics = detail["ai_action_diagnostics"]
    assert diagnostics[0]["action_id"] == "equipment_fault_analysis"
    assert diagnostics[0]["skill_status"] == "available"
    statuses = {item["name"]: item["status"] for item in diagnostics[0]["capabilities"]}
    assert statuses["scada.alarm_query"] == "missing_config"
    assert statuses["cmms.work_order.history"] == "missing_config"
    assert statuses["knowledge.search"] == "platform"
    assert diagnostics[0]["ready"] is False
