import asyncio

import pytest

from agent_platform.domain.models import (
    CapabilityDefinition,
    KnowledgeChunk,
    KnowledgeSource,
    KnowledgeSourceDetail,
    McpServer,
    OutputGuardRule,
    PluginConfig,
    ReleasePlan,
    SecurityEvent,
    TenantProfile,
    ToolOverride,
    UserContext,
    utc_now,
)
from agent_platform.plugins.executors import HttpExecutor, McpExecutor
from agent_platform.runtime.skill_registry import ToolRegistry
from agent_platform.runtime.registry import CapabilityRegistry
from agent_platform.runtime.chat_service import ChatService


class FakeUsers:
    def __init__(self, scopes: list[str]) -> None:
        self.scopes = scopes

    async def get(self, tenant_id: str, user_id: str) -> UserContext:
        return UserContext(
            user_id=user_id,
            tenant_id=tenant_id,
            role="platform_admin",
            scopes=self.scopes,
            email="admin@example.com",
        )


class FakeTenants:
    def __init__(self) -> None:
        self.items = [
            TenantProfile(
                tenant_id="tenant-default",
                name="默认租户",
                package="通用业务包",
                environment="生产",
                budget="100k",
            )
        ]

    async def list_all(self) -> list[TenantProfile]:
        return list(self.items)

    async def get(self, tenant_id: str) -> TenantProfile | None:
        return next((item for item in self.items if item.tenant_id == tenant_id), None)

    async def create(self, tenant: TenantProfile) -> TenantProfile:
        self.items.append(tenant)
        return tenant

    async def update(self, tenant: TenantProfile) -> TenantProfile:
        self.items = [tenant if item.tenant_id == tenant.tenant_id else item for item in self.items]
        return tenant

    async def delete(self, tenant_id: str) -> bool:
        before = len(self.items)
        self.items = [item for item in self.items if item.tenant_id != tenant_id]
        return len(self.items) < before


class FakeKnowledgeSources:
    async def get_detail(self, tenant_id: str, source_id: str) -> KnowledgeSourceDetail | None:
        if source_id != "ks-attrs":
            return None
        source = KnowledgeSource(
            source_id=source_id,
            tenant_id=tenant_id,
            knowledge_base_code="knowledge",
            name="设备 SOP",
            source_type="Markdown",
            owner="ops",
            chunk_count=2,
            status="运行中",
            chunk_attributes_schema={
                "equipment_model": {"type": "string", "indexed": "hot", "filter": "in"},
                "safety_critical": {"type": "boolean", "indexed": "warm", "filter": "eq"},
            },
        )
        chunks = [
            KnowledgeChunk(
                chunk_id="kc-1",
                source_id=source_id,
                tenant_id=tenant_id,
                chunk_index=0,
                title="SOP",
                content="content",
                content_hash="hash-1",
                metadata_json={"attributes": {"equipment_model": "MX-1", "safety_critical": True}},
                token_count=2,
                status="published",
                created_at=utc_now(),
            ),
            KnowledgeChunk(
                chunk_id="kc-2",
                source_id=source_id,
                tenant_id=tenant_id,
                chunk_index=1,
                title="SOP",
                content="content",
                content_hash="hash-2",
                metadata_json={"attributes": {"equipment_model": "MX-1"}},
                token_count=2,
                status="published",
                created_at=utc_now(),
            ),
        ]
        return KnowledgeSourceDetail(source=source, chunks=chunks, content="content")


class FakeToolOverrides:
    def __init__(self) -> None:
        self.items: list[ToolOverride] = []

    async def list_all(self) -> list[ToolOverride]:
        return list(self.items)

    async def upsert(self, override: ToolOverride) -> ToolOverride:
        self.items = [
            item
            for item in self.items
            if not (item.tenant_id == override.tenant_id and item.tool_name == override.tool_name)
        ]
        self.items.append(override)
        return override


class FakeOutputGuardRules:
    def __init__(self) -> None:
        self.items: list[OutputGuardRule] = []

    async def list_all(self) -> list[OutputGuardRule]:
        return list(self.items)

    async def list_enabled(self) -> list[OutputGuardRule]:
        return [item for item in self.items if item.enabled]

    async def upsert(self, rule: OutputGuardRule) -> OutputGuardRule:
        self.items = [item for item in self.items if item.rule_id != rule.rule_id]
        self.items.append(rule)
        return rule


class FakePluginConfigs:
    def __init__(self) -> None:
        self.items: list[PluginConfig] = []

    async def get(self, tenant_id: str, plugin_name: str) -> PluginConfig | None:
        return next(
            (
                item
                for item in self.items
                if item.tenant_id == tenant_id and item.plugin_name == plugin_name
            ),
            None,
        )

    async def upsert(self, plugin_config: PluginConfig) -> PluginConfig:
        self.items = [
            item
            for item in self.items
            if not (item.tenant_id == plugin_config.tenant_id and item.plugin_name == plugin_config.plugin_name)
        ]
        self.items.append(plugin_config)
        return plugin_config


class FakeMcpServers:
    def __init__(self) -> None:
        self.items: list[McpServer] = []

    async def list_all(self) -> list[McpServer]:
        return list(self.items)

    async def get(self, name: str) -> McpServer | None:
        return next((item for item in self.items if item.name == name), None)

    async def upsert(self, server: McpServer) -> McpServer:
        self.items = [item for item in self.items if item.name != server.name]
        self.items.append(server)
        return server

    async def delete(self, name: str) -> bool:
        before = len(self.items)
        self.items = [item for item in self.items if item.name != name]
        return len(self.items) < before


class FakeReleasePlans:
    def __init__(self) -> None:
        self.items = [
            ReleasePlan(
                release_id="rel-1",
                package_id="industry.mfg",
                package_name="工业设备运维助手",
                skill="kb_grounded_qa",
                version="1.2.0",
                status="灰度中",
                rollout_percent=25,
                metric_delta="引用命中 +3.2%",
                started_at=utc_now(),
            )
        ]

    async def list_recent(self) -> list[ReleasePlan]:
        return list(self.items)

    async def update_status(self, release_id: str, *, status: str, rollout_percent: int) -> ReleasePlan | None:
        for item in self.items:
            if item.release_id == release_id:
                item.status = status
                item.rollout_percent = rollout_percent
                return item
        return None


class FakeDrafts:
    async def list_recent(self, tenant_id: str, limit: int = 10) -> list:
        return []


class FakeSecurityEvents:
    def __init__(self) -> None:
        self.saved: list[SecurityEvent] = []

    async def list_recent(self, tenant_id: str) -> list[SecurityEvent]:
        return [
            SecurityEvent(
                event_id="sec-1",
                tenant_id=tenant_id,
                category="safety",
                severity="critical",
                title="安全红线触发",
                status="blocked",
                owner="安全治理组",
            )
        ]

    async def save(self, event: SecurityEvent) -> SecurityEvent:
        self.saved.append(event)
        return event


def build_service(scopes: list[str]) -> ChatService:
    service = ChatService.__new__(ChatService)
    service._users = FakeUsers(scopes)
    service._tenants = FakeTenants()
    service._knowledge_sources = FakeKnowledgeSources()
    service._registry = CapabilityRegistry()
    service._tools = ToolRegistry()
    service._tool_overrides = FakeToolOverrides()
    service._output_guard_rules = FakeOutputGuardRules()
    service._plugin_configs = FakePluginConfigs()
    service._mcp_servers = FakeMcpServers()
    service._releases = FakeReleasePlans()
    service._drafts = FakeDrafts()
    service._security_events = FakeSecurityEvents()
    return service


def test_list_tenants_requires_tenant_management_scope() -> None:
    service = build_service(scopes=["admin:read"])

    with pytest.raises(PermissionError, match="tenant:manage"):
        asyncio.run(service.list_tenants(tenant_id="tenant-default", user_id="user-admin"))


def test_tenant_crud_requires_tenant_management_scope() -> None:
    service = build_service(scopes=["admin:read"])

    with pytest.raises(PermissionError, match="tenant:manage"):
        asyncio.run(
            service.create_tenant(
                name="新租户",
                package="通用业务包",
                environment="生产",
                budget="100k",
                tenant_id="tenant-default",
                user_id="user-admin",
            )
        )

    with pytest.raises(PermissionError, match="tenant:manage"):
        asyncio.run(
            service.update_tenant(
                tenant_id="tenant-default",
                name="默认租户",
                package="通用业务包",
                environment="生产",
                budget="100k",
                active=True,
                auth_tenant_id="tenant-default",
                user_id="user-admin",
            )
        )

    with pytest.raises(PermissionError, match="tenant:manage"):
        asyncio.run(
            service.delete_tenant(
                "tenant-default",
                auth_tenant_id="tenant-default",
                user_id="user-admin",
            )
        )


def test_tenant_management_scope_allows_listing_and_creating_tenants() -> None:
    service = build_service(scopes=["admin:read", "tenant:manage"])

    tenants = asyncio.run(service.list_tenants(tenant_id="tenant-default", user_id="user-admin"))
    created = asyncio.run(
        service.create_tenant(
            name="新租户",
            package="通用业务包",
            environment="生产",
            budget="100k",
            tenant_id="tenant-default",
            user_id="user-admin",
        )
    )

    assert [tenant.tenant_id for tenant in tenants] == ["tenant-default"]
    assert created.name == "新租户"


def test_package_detail_returns_dependency_summary() -> None:
    service = build_service(scopes=["admin:read"])

    detail = asyncio.run(
        service.get_package_detail("industry.finance", tenant_id="tenant-default", user_id="user-admin")
    )

    assert detail["package_id"] == "industry.finance"
    assert detail["dependency_summary"]["plugins"] == 1
    assert detail["dependency_summary"]["common_packages"] == 1


def test_package_impact_marks_incompatible_target() -> None:
    service = build_service(scopes=["admin:read"])

    impact = asyncio.run(
        service.get_package_impact("workflow@0.5.0", tenant_id="tenant-default", user_id="user-admin")
    )

    assert impact["target"] == {"name": "workflow", "version": "0.5.0"}
    assert impact["affected_packages"][0]["package_id"] == "industry.finance"
    assert impact["affected_packages"][0]["compatible"] is False


def test_knowledge_source_attributes_include_hit_rates() -> None:
    service = build_service(scopes=["admin:read"])

    response = asyncio.run(
        service.get_knowledge_source_attributes("ks-attrs", tenant_id="tenant-default", user_id="user-admin")
    )
    fields = {item["field"]: item for item in response["fields"]}

    assert fields["equipment_model"]["hit_rate"] == 1
    assert fields["safety_critical"]["hit_rate"] == 0.5


def test_plugin_config_rejects_plain_secret_value() -> None:
    service = build_service(scopes=["admin:read", "tenant:manage"])

    schema = asyncio.run(
        service.get_plugin_config_schema("hr.leave.balance.query", tenant_id="tenant-default", user_id="user-admin")
    )
    assert schema["config_schema"]["properties"]["auth_ref"]["format"] == "secret-ref"

    with pytest.raises(ValueError, match="Invalid secret reference"):
        asyncio.run(
            service.update_plugin_config(
                "hr.leave.balance.query",
                config={"endpoint": "https://hr.local", "auth_ref": "plain-token", "timeout_ms": 3000},
                tenant_id="tenant-default",
                user_id="user-admin",
            )
        )


def test_plugin_config_update_persists_to_repository() -> None:
    service = build_service(scopes=["admin:read", "tenant:manage"])

    updated = asyncio.run(
        service.update_plugin_config(
            "hr.leave.balance.query",
            config={"endpoint": "https://hr.local", "auth_ref": "secrets/hr_demo_token", "timeout_ms": 3000},
            tenant_id="tenant-default",
            user_id="user-admin",
        )
    )
    schema = asyncio.run(
        service.get_plugin_config_schema("hr.leave.balance.query", tenant_id="tenant-default", user_id="user-admin")
    )

    assert updated["config"] == {
        "endpoint": "https://hr.local",
        "auth_ref": "secrets/hr_demo_token",
        "timeout_ms": 3000,
    }
    assert schema["config"] == updated["config"]


def test_plugin_config_masks_nested_secrets_and_preserves_existing_value() -> None:
    service = build_service(scopes=["admin:read", "tenant:manage"])
    plugin = HttpExecutor(
        CapabilityDefinition(
            name="cmms.work_order.history",
            description="CMMS work order history",
            risk_level="low",
            side_effect_level="read",
            required_scope="cmms:read",
            input_schema={"required": ["equipment_id"]},
            output_schema={"required": ["workorders"]},
            source="package",
            package_id="industry.mfg_maintenance",
        ),
        package_id="industry.mfg_maintenance",
        plugin_name="cmms.work_order",
        binding={},
        plugin_config_schema={
            "endpoint": {"type": "string", "required": True},
            "secrets": {
                "type": "object",
                "required": True,
                "properties": {
                    "cmms_token": {"type": "string", "required": True},
                },
            },
            "timeout_ms": {"type": "integer", "default": 5000},
        },
    )
    service._registry._package_plugins = {"cmms.work_order.history": plugin}

    updated = asyncio.run(
        service.update_plugin_config(
            "cmms.work_order",
            config={
                "endpoint": "https://cmms.local",
                "secrets": {"cmms_token": "token-123456"},
                "timeout_ms": 3000,
            },
            tenant_id="tenant-default",
            user_id="user-admin",
        )
    )
    saved = asyncio.run(service._plugin_configs.get("tenant-default", "cmms.work_order"))
    schema = asyncio.run(
        service.get_plugin_config_schema("cmms.work_order", tenant_id="tenant-default", user_id="user-admin")
    )

    assert updated["config"]["secrets"] == {"cmms_token": "***3456"}
    assert schema["config"]["secrets"] == {"cmms_token": "***3456"}
    assert saved is not None
    assert saved.config["secrets"] == {"cmms_token": "token-123456"}

    preserved = asyncio.run(
        service.update_plugin_config(
            "cmms.work_order",
            config={
                "endpoint": "https://cmms.local",
                "secrets": {"cmms_token": "***3456"},
                "timeout_ms": 4000,
            },
            tenant_id="tenant-default",
            user_id="user-admin",
        )
    )
    saved_after_mask_submit = asyncio.run(service._plugin_configs.get("tenant-default", "cmms.work_order"))

    assert preserved["config"]["timeout_ms"] == 4000
    assert saved_after_mask_submit is not None
    assert saved_after_mask_submit.config["secrets"] == {"cmms_token": "token-123456"}


def test_mcp_server_registry_resolves_into_capability_tenant_config() -> None:
    service = build_service(scopes=["admin:read", "tenant:manage"])
    service._registry._package_plugins = {
        "mcp.test.search": McpExecutor(
            CapabilityDefinition(
                name="mcp.test.search",
                description="MCP registry resolution test capability",
                risk_level="low",
                side_effect_level="read",
                required_scope="mcp:read",
                input_schema={"required": ["query"]},
                output_schema={"required": ["answer"]},
                source="package",
                package_id="pkg.test_mcp",
            ),
            package_id="pkg.test_mcp",
            plugin_name="mcp.test",
            binding={},
        )
    }
    asyncio.run(
        service._mcp_servers.upsert(
            McpServer(
                server_id="mcp-test",
                name="registered",
                transport="streamable-http",
                endpoint="https://mcp.test/mcp",
                auth_ref="",
                headers={"Authorization": "Bearer $secret.token"},
                status="active",
            )
        )
    )
    asyncio.run(
        service._plugin_configs.upsert(
            PluginConfig(
                tenant_id="tenant-default",
                plugin_name="mcp.test",
                config={"mcp_server": "registered", "secrets": {"token": "secret-token"}},
            )
        )
    )

    config = asyncio.run(
        service._load_capability_tenant_config(
            tenant_id="tenant-default",
            capability_name="mcp.test.search",
        )
    )

    assert config["mcp_server"] == "registered"
    assert config["secrets"] == {"token": "secret-token"}
    assert config["mcp_servers"] == {
        "registered": {
            "transport": "streamable-http",
            "endpoint": "https://mcp.test/mcp",
            "headers": {"Authorization": "Bearer $secret.token"},
            "status": "active",
        }
    }


def test_tool_override_update_persists_override() -> None:
    service = build_service(scopes=["admin:read", "tenant:manage"])

    updated = asyncio.run(
        service.update_tool_override(
            target_tenant_id="tenant-default",
            tool_name="http_fetch",
            quota=12,
            timeout=1500,
            disabled=True,
            tenant_id="tenant-default",
            user_id="user-admin",
        )
    )

    assert updated["tenant_id"] == "tenant-default"
    assert updated["tool_name"] == "http_fetch"
    assert updated["quota"] == 12
    assert updated["timeout"] == 1500
    assert updated["disabled"] is True
    assert updated["overridden"] is True


def test_security_overview_uses_persisted_output_guard_rules() -> None:
    service = build_service(scopes=["admin:read"])
    asyncio.run(
        service._output_guard_rules.upsert(
            OutputGuardRule(
                rule_id="mfg.output_guard.loto",
                package_id="industry.mfg",
                pattern="LOTO|挂牌上锁",
                action="block_or_escalate",
                source="industry.mfg",
            )
        )
    )

    overview = asyncio.run(service.list_security_overview(tenant_id="tenant-default", user_id="user-admin"))

    assert overview["redlines"] == [
        {
            "rule_id": "mfg.output_guard.loto",
            "package_id": "industry.mfg",
            "pattern": "LOTO|挂牌上锁",
            "action": "block_or_escalate",
            "source": "industry.mfg",
            "enabled": True,
            "recent_triggers": 1,
        }
    ]


def test_output_guard_rule_update_persists_rule() -> None:
    service = build_service(scopes=["admin:read", "tenant:manage"])

    updated = asyncio.run(
        service.update_output_guard_rule(
            rule_id="mfg.output_guard.loto",
            package_id="industry.mfg",
            pattern="LOTO|挂牌上锁",
            action="block_or_escalate",
            source="industry.mfg",
            enabled=False,
            tenant_id="tenant-default",
            user_id="user-admin",
        )
    )
    overview = asyncio.run(service.list_security_overview(tenant_id="tenant-default", user_id="user-admin"))

    assert updated["rule_id"] == "mfg.output_guard.loto"
    assert updated["enabled"] is False
    assert overview["redlines"][0]["enabled"] is False


def test_output_guard_rule_update_rejects_unknown_action() -> None:
    service = build_service(scopes=["admin:read", "tenant:manage"])

    with pytest.raises(ValueError, match="Unsupported output guard action"):
        asyncio.run(
            service.update_output_guard_rule(
                rule_id="mfg.output_guard.invalid",
                package_id="industry.mfg",
                pattern="LOTO",
                action="silent_allow",
                source="industry.mfg",
                enabled=True,
                tenant_id="tenant-default",
                user_id="user-admin",
            )
        )


def test_release_plan_update_persists_status() -> None:
    service = build_service(scopes=["admin:read", "tenant:manage"])

    updated = asyncio.run(
        service.update_release_plan(
            "rel-1",
            status="已完成",
            rollout_percent=100,
            tenant_id="tenant-default",
            user_id="user-admin",
        )
    )
    overview = asyncio.run(service.list_release_plans(tenant_id="tenant-default", user_id="user-admin"))

    assert updated["release_id"] == "rel-1"
    assert updated["status"] == "已完成"
    assert updated["rollout_percent"] == 100
    assert overview["releases"][0]["status"] == "已完成"


def test_release_plan_update_rejects_inconsistent_completed_percent() -> None:
    service = build_service(scopes=["admin:read", "tenant:manage"])

    with pytest.raises(ValueError, match="completed release"):
        asyncio.run(
            service.update_release_plan(
                "rel-1",
                status="已完成",
                rollout_percent=80,
                tenant_id="tenant-default",
                user_id="user-admin",
            )
        )
