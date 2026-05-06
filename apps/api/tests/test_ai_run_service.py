from __future__ import annotations

import asyncio
from dataclasses import asdict
from typing import Any

import pytest

from agent_platform.domain.models import (
    AIActionDefinition,
    AIRun,
    BusinessOutput,
    CapabilityDefinition,
    SkillDefinition,
    SourceReference,
    TenantProfile,
    TraceRecord,
    UserContext,
)
from agent_platform.plugins.base import CapabilityPlugin
from agent_platform.plugins.executors.http import HttpExecutor
from agent_platform.plugins.stub import StubPackagePlugin
from agent_platform.runtime.data_input import DataInput
from agent_platform.runtime.ai_run_service import AIRunService
from agent_platform.runtime.registry import CapabilityRegistry
from agent_platform.runtime.skill_registry import ToolRegistry


class EmptyLoader:
    def list_packages(self) -> list[dict[str, Any]]:
        return []


class StaticActionRegistry:
    def __init__(self, action: AIActionDefinition) -> None:
        self.action = action

    def list_actions(self, package_id: str | None = None) -> list[AIActionDefinition]:
        if package_id and package_id != self.action.package_id:
            return []
        return [self.action]

    def get(self, package_id: str, action_id: str) -> AIActionDefinition | None:
        if package_id == self.action.package_id and action_id == self.action.id:
            return self.action
        return None

    def list_business_objects(self, package_id: str | None = None) -> list[dict[str, object]]:
        if package_id and package_id != self.action.package_id:
            return []
        return [
            {
                "package_id": self.action.package_id,
                "type": "equipment",
                "label": "设备",
                "id_field": "equipment_id",
                "lookup_capability": "equipment.lookup",
            }
        ]

    def get_business_object(self, package_id: str, object_type: str) -> dict[str, object] | None:
        for item in self.list_business_objects(package_id):
            if item["type"] == object_type:
                return item
        return None


class StaticSkillRegistry:
    def __init__(self, skill: SkillDefinition) -> None:
        self.skill = skill

    def get(self, name: str) -> SkillDefinition | None:
        if name in {self.skill.name, f"{self.skill.package_id}::{self.skill.name}"}:
            return self.skill
        return None


class MemoryRunRepository:
    def __init__(self) -> None:
        self.items: dict[str, AIRun] = {}

    async def create(self, run: AIRun) -> AIRun:
        self.items[run.run_id] = run
        return run

    async def update(self, run: AIRun) -> AIRun:
        self.items[run.run_id] = run
        return run

    async def get(self, tenant_id: str, run_id: str) -> AIRun | None:
        run = self.items.get(run_id)
        return run if run and run.tenant_id == tenant_id else None

    async def list_recent(self, tenant_id: str, limit: int = 20) -> list[AIRun]:
        return [item for item in self.items.values() if item.tenant_id == tenant_id][:limit]


class MemoryTraceRepository:
    def __init__(self) -> None:
        self.items: dict[str, TraceRecord] = {}

    async def save(self, trace: TraceRecord) -> TraceRecord:
        self.items[trace.trace_id] = trace
        return trace

    async def get(self, trace_id: str) -> TraceRecord | None:
        return self.items.get(trace_id)

    async def list_recent(self, tenant_id: str, limit: int = 20) -> list[TraceRecord]:
        return [item for item in self.items.values() if item.tenant_id == tenant_id][:limit]


class MemoryBusinessOutputRepository:
    def __init__(self) -> None:
        self.items: dict[str, BusinessOutput] = {}

    async def create(self, output: BusinessOutput) -> BusinessOutput:
        # 保证 payload 可以进入 JSON/数据库层，不携带 dataclass 对象。
        asdict(output)
        self.items[output.output_id] = output
        return output

    async def update(self, output: BusinessOutput) -> BusinessOutput:
        self.items[output.output_id] = output
        return output

    async def get(self, tenant_id: str, output_id: str) -> BusinessOutput | None:
        output = self.items.get(output_id)
        return output if output and output.tenant_id == tenant_id else None

    async def list_for_tenant(self, tenant_id: str, **_: object) -> list[BusinessOutput]:
        return [item for item in self.items.values() if item.tenant_id == tenant_id]


class StaticTenantRepository:
    async def get(self, tenant_id: str) -> TenantProfile | None:
        return TenantProfile(
            tenant_id=tenant_id,
            name="测试租户",
            package="industry.mfg_maintenance",
            environment="test",
            budget="0",
            active=True,
        )


class StaticUserRepository:
    async def get(self, tenant_id: str, user_id: str) -> UserContext | None:
        return UserContext(
            user_id=user_id,
            tenant_id=tenant_id,
            role="tester",
            scopes=["cmms:read", "knowledge:read"],
        )


class EmptyPluginConfigRepository:
    async def get(self, tenant_id: str, plugin_name: str) -> None:
        return None


class WorkOrderHistoryPlugin(CapabilityPlugin):
    capability = CapabilityDefinition(
        name="cmms.work_order.history",
        description="测试用 CMMS 历史工单查询",
        risk_level="low",
        side_effect_level="read",
        required_scope="cmms:read",
        input_schema={"required": ["equipment_id"]},
        output_schema={"required": ["workorders"]},
        source="package",
        package_id="industry.mfg_maintenance",
    )
    plugin_name = "cmms.work_order"

    def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "workorders": [
                {
                    "work_order_id": "wo-test-1",
                    "equipment_id": payload["equipment_id"],
                    "fault_code": payload.get("fault_code"),
                    "summary": "历史工单记录",
                }
            ],
            "_meta": {"executor": "http", "status": 200},
        }


class EquipmentLookupPlugin(CapabilityPlugin):
    capability = CapabilityDefinition(
        name="equipment.lookup",
        description="测试用设备对象查询",
        risk_level="low",
        side_effect_level="read",
        required_scope="cmms:read",
        input_schema={"required": ["equipment_id"]},
        output_schema={"required": ["equipment"]},
        source="package",
        package_id="industry.mfg_maintenance",
    )
    plugin_name = "cmms.work_order"

    def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload["equipment_id"] == "EQ-CNC-650-01":
            return {
                "equipment": {
                    "equipment_id": "EQ-CNC-650-01",
                    "name": "CNC 加工中心 1#",
                },
                "total": 1,
            }
        return {"equipment": None, "total": 0}


class KnowledgeFixturePlugin(CapabilityPlugin):
    capability = CapabilityDefinition(
        name="knowledge.search",
        description="测试用知识检索",
        risk_level="low",
        side_effect_level="read",
        required_scope="knowledge:read",
        input_schema={"required": ["query"]},
        output_schema={"required": ["matches"]},
        source="_platform",
    )

    def invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "matches": [
                SourceReference(
                    id="kb-test-1",
                    title="测试知识条目",
                    snippet=f"匹配查询：{payload['query']}",
                    source_type="knowledge",
                )
            ]
        }


def build_service(*, registry: CapabilityRegistry, skill: SkillDefinition) -> tuple[AIRunService, MemoryRunRepository, MemoryTraceRepository, MemoryBusinessOutputRepository]:
    runs = MemoryRunRepository()
    traces = MemoryTraceRepository()
    outputs = MemoryBusinessOutputRepository()
    action = AIActionDefinition(
        id="equipment_fault_analysis",
        label="故障分析",
        package_id="industry.mfg_maintenance",
        object_types=["equipment"],
        skill=skill.name,
        required_inputs=["equipment_id"],
        optional_inputs=["fault_code", "query"],
        outputs=["recommendation", "action_plan"],
        data_input_modes=["platform_pull"],
    )
    service = AIRunService(
        actions=StaticActionRegistry(action),  # type: ignore[arg-type]
        runs=runs,
        registry=registry,
        skills=StaticSkillRegistry(skill),  # type: ignore[arg-type]
        tools=ToolRegistry(),
        traces=traces,
        tenants=StaticTenantRepository(),  # type: ignore[arg-type]
        users=StaticUserRepository(),  # type: ignore[arg-type]
        plugin_configs=EmptyPluginConfigRepository(),  # type: ignore[arg-type]
        business_outputs=outputs,
    )
    return service, runs, traces, outputs


def fault_triage_skill() -> SkillDefinition:
    return SkillDefinition(
        name="fault_triage",
        description="测试用故障分析 skill",
        version="1.0.0",
        source="package",
        package_id="industry.mfg_maintenance",
        steps=[
            {
                "id": "alarms",
                "capability": "scada.alarm_query",
                "input": {"equipment_id": "$inputs.equipment_id"},
            },
            {
                "id": "history",
                "capability": "cmms.work_order.history",
                "input": {
                    "equipment_id": "$inputs.equipment_id",
                    "fault_code": "$inputs.fault_code",
                },
            },
            {
                "id": "knowledge",
                "capability": "knowledge.search",
                "input": {"query": "$inputs.query"},
            },
        ],
        outputs_mapping={
            "summary": "已完成设备 $inputs.equipment_id 的故障排查编排。",
            "alarms": "$steps.alarms.alarms",
            "workorders": "$steps.history.workorders",
            "knowledge_matches": "$steps.knowledge.matches",
        },
    )


def test_ai_run_service_saves_structured_output_and_marks_stub() -> None:
    registry = CapabilityRegistry(loader=EmptyLoader())  # type: ignore[arg-type]
    scada_capability = CapabilityDefinition(
        name="scada.alarm_query",
        description="测试用 SCADA 报警查询",
        risk_level="low",
        side_effect_level="read",
        required_scope="scada:read",
        input_schema={"required": ["equipment_id"]},
        output_schema={"required": ["alarms"]},
        source="package",
        package_id="industry.mfg_maintenance",
    )
    registry._package_plugins = {
        "scada.alarm_query": StubPackagePlugin(
            scada_capability,
            package_id="industry.mfg_maintenance",
            plugin_name="scada.alarm_query",
        ),
        "cmms.work_order.history": WorkOrderHistoryPlugin(),
        "knowledge.search": KnowledgeFixturePlugin(),
    }
    service, _runs, traces, outputs = build_service(registry=registry, skill=fault_triage_skill())

    response = asyncio.run(
        service.run_action(
            tenant_id="tenant-a",
            user_id="user-a",
            package_id="industry.mfg_maintenance",
            action_id="equipment_fault_analysis",
            source="workspace",
            object_type="equipment",
            object_id="CNC-01",
            inputs={"fault_code": "AX-203"},
            data_input=DataInput(),
        )
    )

    run = response["run"]
    assert run["status"] == "succeeded"
    output = next(iter(outputs.items.values()))
    assert output.run_id == run["run_id"]
    assert output.payload["facts"]
    assert output.payload["citations"][0]["id"]
    assert output.payload["recommendations"]
    assert output.payload["action_plan"]
    assert output.payload["runtime_warnings"] == ["alarms: scada.alarm_query 当前返回 stub 占位结果"]
    trace = traces.items[run["trace_id"]]
    assert any(step.status == "stub" and step.ref == "scada.alarm_query" for step in trace.steps)


def test_ai_run_service_records_failed_step_when_config_missing() -> None:
    registry = CapabilityRegistry(loader=EmptyLoader())  # type: ignore[arg-type]
    capability = CapabilityDefinition(
        name="cmms.work_order.history",
        description="测试用 CMMS 历史工单查询",
        risk_level="low",
        side_effect_level="read",
        required_scope="cmms:read",
        input_schema={"required": ["equipment_id"]},
        output_schema={"required": ["workorders"]},
        source="package",
        package_id="industry.mfg_maintenance",
    )
    registry._package_plugins = {
        "cmms.work_order.history": HttpExecutor(
            capability,
            package_id="industry.mfg_maintenance",
            plugin_name="cmms.work_order",
            binding={"method": "GET", "path": "/api/v1/workorders"},
        )
    }
    skill = SkillDefinition(
        name="fault_triage",
        description="测试用故障分析 skill",
        version="1.0.0",
        source="package",
        package_id="industry.mfg_maintenance",
        steps=[
            {
                "id": "history",
                "capability": "cmms.work_order.history",
                "input": {"equipment_id": "$inputs.equipment_id"},
            }
        ],
        outputs_mapping={"workorders": "$steps.history.workorders"},
    )
    service, _runs, traces, _outputs = build_service(registry=registry, skill=skill)

    response = asyncio.run(
        service.run_action(
            tenant_id="tenant-a",
            user_id="user-a",
            package_id="industry.mfg_maintenance",
            action_id="equipment_fault_analysis",
            source="workspace",
            object_type="equipment",
            object_id="CNC-01",
            inputs={},
            data_input=DataInput(),
        )
    )

    run = response["run"]
    assert run["status"] == "failed"
    assert "MISSING_CONFIG" in run["error_message"]
    trace = traces.items[run["trace_id"]]
    assert any(step.name == "skill_step:history" and step.status == "failed" for step in trace.steps)
    assert trace.steps[-1].name == "ai_action_failed"


def test_ai_run_service_looks_up_business_object_before_action() -> None:
    registry = CapabilityRegistry(loader=EmptyLoader())  # type: ignore[arg-type]
    registry._package_plugins = {"equipment.lookup": EquipmentLookupPlugin()}
    service, _runs, _traces, _outputs = build_service(registry=registry, skill=fault_triage_skill())

    response = asyncio.run(
        service.lookup_business_object(
            tenant_id="tenant-a",
            user_id="user-a",
            package_id="industry.mfg_maintenance",
            object_type="equipment",
            object_id="EQ-CNC-650-01",
        )
    )

    assert response["lookup_capability"] == "equipment.lookup"
    assert response["result"]["equipment"]["name"] == "CNC 加工中心 1#"


def test_ai_run_service_rejects_object_lookup_without_declaration() -> None:
    registry = CapabilityRegistry(loader=EmptyLoader())  # type: ignore[arg-type]
    service, _runs, _traces, _outputs = build_service(registry=registry, skill=fault_triage_skill())

    with pytest.raises(ValueError, match="not declared"):
        asyncio.run(
            service.lookup_business_object(
                tenant_id="tenant-a",
                user_id="user-a",
                package_id="industry.mfg_maintenance",
                object_type="asset",
                object_id="asset-1",
            )
        )
