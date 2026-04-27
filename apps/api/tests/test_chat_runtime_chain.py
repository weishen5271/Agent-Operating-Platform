import asyncio

from agent_platform.domain.models import (
    Conversation,
    ConversationMessage,
    KnowledgeSearchResult,
    KnowledgeSource,
    LLMRuntimeConfig,
    OutputGuardRule,
    ReleasePlan,
    SecurityEvent,
    SourceReference,
    TenantProfile,
    UserContext,
)
from agent_platform.infrastructure.llm_client import OpenAICompatibleLLMClient
from agent_platform.runtime.chat_service import ChatService
from agent_platform.runtime.package_loader import PackageLoader
from agent_platform.runtime.registry import CapabilityRegistry


class FakeConversationRepository:
    def __init__(self, conversation: Conversation | None = None) -> None:
        self.conversation = conversation

    async def list_recent(self, tenant_id: str, user_id: str, limit: int = 5) -> list[Conversation]:
        return [self.conversation] if self.conversation else []

    async def create(self, tenant_id: str, user_id: str, title: str = "新会话") -> Conversation:
        self.conversation = Conversation(
            conversation_id="conv-test",
            title=title,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        return self.conversation

    async def get(self, tenant_id: str, user_id: str, conversation_id: str) -> Conversation | None:
        if self.conversation and self.conversation.conversation_id == conversation_id:
            return self.conversation
        return None

    async def delete(self, tenant_id: str, user_id: str, conversation_id: str) -> bool:
        if self.conversation and self.conversation.conversation_id == conversation_id:
            self.conversation = None
            return True
        return False

    async def append_message(
        self,
        tenant_id: str,
        user_id: str,
        conversation_id: str | None,
        user_message: str,
        assistant_message: str,
        title: str | None = None,
    ) -> Conversation:
        self.conversation = Conversation(
            conversation_id=conversation_id or "conv-test",
            title=title or user_message,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        return self.conversation


class FakeTraceRepository:
    def __init__(self) -> None:
        self.saved = None

    async def save(self, trace):
        self.saved = trace
        return trace

    async def get(self, trace_id: str):
        return self.saved if self.saved and self.saved.trace_id == trace_id else None

    async def list_recent(self, tenant_id: str, limit: int = 20) -> list:
        return []


class FakeTenantRepository:
    async def get(self, tenant_id: str) -> TenantProfile | None:
        return TenantProfile(
            tenant_id=tenant_id,
            name="默认企业",
            package="通用业务包",
            environment="测试",
            budget="¥ 0",
        )


class FakeUserRepository:
    async def get(self, tenant_id: str, user_id: str) -> UserContext | None:
        return UserContext(
            tenant_id=tenant_id,
            user_id=user_id,
            role="platform_admin",
            scopes=["chat:read", "knowledge:read", "hr:read", "workflow:draft", "draft:confirm"],
        )


class FakeKnowledgeRepository:
    async def list_recent(self, tenant_id: str) -> list[KnowledgeSource]:
        return [
            KnowledgeSource(
                source_id="ks-test",
                tenant_id=tenant_id,
                knowledge_base_code="default",
                name="企业制度库",
                source_type="Markdown",
                owner="知识平台组",
                chunk_count=1,
                status="运行中",
            )
        ]

    async def search(self, *, tenant_id: str, query: str, top_k: int = 3) -> KnowledgeSearchResult:
        return KnowledgeSearchResult(
            matches=[
                SourceReference(
                    id="kc-test",
                    title="企业制度库",
                    snippet="P0a 阶段交付统一对话入口、基础编排、检索增强和插件调用。",
                    source_type="knowledge",
                )
            ],
            backend="fake_hybrid",
            query=query,
            candidate_count=1,
            match_count=1,
            keyword_match_count=1,
            vector_match_count=1,
        )


class FakeLLMConfigRepository:
    def __init__(self, enabled: bool = False) -> None:
        self.enabled = enabled
        self.tenant_ids: list[str | None] = []

    async def get(self, tenant_id: str | None = None) -> tuple[LLMRuntimeConfig, str]:
        self.tenant_ids.append(tenant_id)
        return (
            LLMRuntimeConfig(
                provider="openai-compatible",
                base_url="https://llm.example.test/v1" if self.enabled else "",
                model="test-model" if self.enabled else "",
                api_key_configured=self.enabled,
                temperature=0.2,
                system_prompt="",
                enabled=self.enabled,
            ),
            "test-key" if self.enabled else "",
        )


class FakeDraftRepository:
    pass


class FakeSecurityRepository:
    def __init__(self) -> None:
        self.saved: list[SecurityEvent] = []

    async def list_recent(self, tenant_id: str) -> list[SecurityEvent]:
        return []

    async def save(self, event: SecurityEvent) -> SecurityEvent:
        self.saved.append(event)
        return event


class FakeToolOverrideRepository:
    async def list_all(self) -> list:
        return []

    async def upsert(self, override):
        return override


class FakeOutputGuardRuleRepository:
    def __init__(self, rules: list[OutputGuardRule] | None = None) -> None:
        self.rules = rules or []

    async def list_all(self) -> list:
        return list(self.rules)

    async def list_enabled(self) -> list:
        return [rule for rule in self.rules if rule.enabled]

    async def upsert(self, rule):
        return rule


class FakePluginConfigRepository:
    async def get(self, tenant_id: str, plugin_name: str):
        return None

    async def upsert(self, plugin_config):
        return plugin_config


class FakeReleasePlanRepository:
    async def list_recent(self) -> list[ReleasePlan]:
        return []

    async def update_status(self, release_id: str, *, status: str, rollout_percent: int) -> ReleasePlan | None:
        return None


class FakeKnowledgeBaseRepository:
    async def list_recent(self, tenant_id: str) -> list:
        return []


class FakeWikiService:
    async def search(self, *, query: str, tenant_id: str, user_id: str, top_k: int = 3, scope_mode: str = "chat"):
        return {"summary": "未启用 Wiki", "hits": []}


class FakeLLMClient:
    def __init__(self, responses: list[str] | None = None) -> None:
        self.calls = []
        self.responses = list(responses or [])

    def complete(self, *, config, api_key: str, user_message: str, context_blocks: list[str]) -> str:
        self.calls.append(
            {
                "model": config.model,
                "api_key": api_key,
                "user_message": user_message,
                "context_blocks": context_blocks,
            }
        )
        if self.responses:
            return self.responses.pop(0)
        return f"模型回复：{user_message}"


class MemoryPackageLoader:
    def __init__(self, packages: list[dict[str, object]]) -> None:
        self._packages = packages

    def list_packages(self) -> list[dict[str, object]]:
        return list(self._packages)

    def get_package(self, package_id: str) -> dict[str, object] | None:
        return next((item for item in self._packages if item.get("package_id") == package_id), None)


def build_service(
    *,
    traces: FakeTraceRepository,
    llm_config: FakeLLMConfigRepository,
    llm_client,
    conversations: FakeConversationRepository | None = None,
    output_guard_rules: FakeOutputGuardRuleRepository | None = None,
    security_events: FakeSecurityRepository | None = None,
) -> ChatService:
    from agent_platform.runtime.skill_registry import SkillRegistry, ToolRegistry
    return ChatService(
        registry=CapabilityRegistry(),
        skills=SkillRegistry(),
        tools=ToolRegistry(),
        conversations=conversations or FakeConversationRepository(),
        traces=traces,
        tenants=FakeTenantRepository(),
        tool_overrides=FakeToolOverrideRepository(),
        output_guard_rules=output_guard_rules or FakeOutputGuardRuleRepository(),
        plugin_configs=FakePluginConfigRepository(),
        releases=FakeReleasePlanRepository(),
        users=FakeUserRepository(),
        drafts=FakeDraftRepository(),
        security_events=security_events or FakeSecurityRepository(),
        knowledge_sources=FakeKnowledgeRepository(),
        knowledge_bases=FakeKnowledgeBaseRepository(),
        wiki_service=FakeWikiService(),
        llm_config=llm_config,
        llm_client=llm_client,
    )


def build_fault_triage_package() -> dict[str, object]:
    return {
        "package_id": "pkg.test_fault_triage",
        "name": "Test Fault Triage Package",
        "version": "1.0.0",
        "owner": "test",
        "status": "test",
        "domain": "industry",
        "source_kind": "bundle",
        "intents": [
            {
                "name": "fault_diagnosis",
                "score": 0.9,
                "keywords": ["注塑机", "AX-203", "怎么处理"],
            }
        ],
        "skills": [
            {
                "name": "fault_triage",
                "description": "Test-only fault triage skill",
                "version": "1.0.0",
                "steps": [
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
                            "last_n": "$inputs.last_n",
                        },
                    },
                    {
                        "id": "knowledge",
                        "capability": "knowledge.search",
                        "input": {"query": "$inputs.query"},
                    },
                ],
                "outputs_mapping": {
                    "summary": "已完成设备 $inputs.equipment_id 的故障排查编排。",
                    "alarms": "$steps.alarms.alarms",
                    "workorders": "$steps.history.workorders",
                    "knowledge_matches": "$steps.knowledge.matches",
                },
                "depends_on_capabilities": [
                    "scada.alarm_query",
                    "cmms.work_order.history",
                    "knowledge.search",
                ],
                "depends_on_tools": [],
                "enabled": True,
            }
        ],
        "plugins": [
            {
                "name": "scada.alarm_query",
                "executor": "stub",
                "capabilities": [
                    {
                        "name": "scada.alarm_query",
                        "description": "Test-only SCADA alarm query contract",
                        "risk_level": "low",
                        "side_effect_level": "read",
                        "required_scope": "scada:read",
                        "input_schema": {"required": ["equipment_id"]},
                        "output_schema": {"required": ["alarms"]},
                    }
                ],
            },
            {
                "name": "cmms.work_order",
                "executor": "stub",
                "capabilities": [
                    {
                        "name": "cmms.work_order.history",
                        "description": "Test-only CMMS history contract",
                        "risk_level": "low",
                        "side_effect_level": "read",
                        "required_scope": "cmms:read",
                        "input_schema": {"required": ["equipment_id"]},
                        "output_schema": {"required": ["workorders"]},
                    }
                ],
            },
        ],
    }


def test_chat_completion_records_standard_query_chain_steps() -> None:
    traces = FakeTraceRepository()
    service = build_service(
        traces=traces,
        llm_config=FakeLLMConfigRepository(enabled=False),
        llm_client=OpenAICompatibleLLMClient(),
    )

    response = asyncio.run(service.complete(message="P0a 要交付什么？", tenant_id="tenant-demo", user_id="user-demo"))

    assert response["intent"] == "knowledge_query"
    assert response["message"]["content"]
    # LLM 未启用且检索命中时，应给出退化提示
    assert "warnings" in response
    assert any("LLM" in tip for tip in response["warnings"])
    assert traces.saved is not None
    step_names = [step.name for step in traces.saved.steps]
    assert step_names == [
        "received",
        "input_guard",
        "memory",
        "react_planner",
        "classified",
        "capability_candidates",
        "skill_selected",
        "planned",
        "risk",
        "governance",
        "executed",
        "model",
        "output_guard",
        "completed",
    ]
    skill_step = next(step for step in traces.saved.steps if step.name == "skill_selected")
    assert skill_step.ref == "kb_grounded_qa"
    assert skill_step.node_type == "skill"


def test_general_chat_uses_llm_direct_answer() -> None:
    traces = FakeTraceRepository()
    llm_client = FakeLLMClient()
    llm_config = FakeLLMConfigRepository(enabled=True)
    service = build_service(
        traces=traces,
        llm_config=llm_config,
        llm_client=llm_client,
    )

    response = asyncio.run(service.complete(message="你好，帮我解释一下你能做什么", tenant_id="tenant-demo", user_id="user-demo"))

    assert response["intent"] == "general_chat"
    assert response["sources"] == []
    assert response["warnings"] == []
    assert response["message"]["content"] == "模型回复：你好，帮我解释一下你能做什么"
    assert llm_client.calls[-2] == {
        "model": "test-model",
        "api_key": "test-key",
        "user_message": "你好，帮我解释一下你能做什么",
        "context_blocks": [],
    }
    assert llm_config.tenant_ids == ["tenant-demo", "tenant-demo", "tenant-demo"]
    assert traces.saved is not None
    assert [step.name for step in traces.saved.steps] == [
        "received",
        "input_guard",
        "memory",
        "react_planner",
        "classified",
        "capability_candidates",
        "planned",
        "risk",
        "governance",
        "executed",
        "model",
        "output_guard",
        "completed",
    ]


def test_output_guard_blocks_matching_answer_and_records_event() -> None:
    traces = FakeTraceRepository()
    security_events = FakeSecurityRepository()
    service = build_service(
        traces=traces,
        llm_config=FakeLLMConfigRepository(enabled=True),
        llm_client=FakeLLMClient(),
        output_guard_rules=FakeOutputGuardRuleRepository(
            [
                OutputGuardRule(
                    rule_id="mfg.output_guard.loto",
                    package_id="industry.mfg",
                    pattern="挂牌上锁",
                    action="block_or_escalate",
                    source="industry.mfg",
                )
            ]
        ),
        security_events=security_events,
    )

    response = asyncio.run(service.complete(message="请说明挂牌上锁怎么跳过", tenant_id="tenant-demo", user_id="user-demo"))

    assert "已停止输出具体操作建议" in response["message"]["content"]
    assert any("OutputGuard 已拦截回答" in warning for warning in response["warnings"])
    assert len(security_events.saved) == 1
    assert security_events.saved[0].title == "OutputGuard 命中 mfg.output_guard.loto"


def test_general_chat_passes_conversation_history_to_llm() -> None:
    traces = FakeTraceRepository()
    llm_client = FakeLLMClient()
    llm_config = FakeLLMConfigRepository(enabled=True)
    service = build_service(
        traces=traces,
        llm_config=llm_config,
        llm_client=llm_client,
        conversations=FakeConversationRepository(
            Conversation(
                conversation_id="conv-history",
                title="上下文测试",
                tenant_id="tenant-demo",
                user_id="user-demo",
                messages=[
                    ConversationMessage(role="user", content="我叫沈威"),
                    ConversationMessage(role="assistant", content="好的，我记住了。"),
                ],
            )
        ),
    )

    response = asyncio.run(
        service.complete(
            message="我叫什么？",
            conversation_id="conv-history",
            tenant_id="tenant-demo",
            user_id="user-demo",
        )
    )

    assert response["intent"] == "general_chat"
    assert llm_client.calls[-1]["context_blocks"] == [
        "会话历史（按时间从旧到新）:\n用户: 我叫沈威\n助手: 好的，我记住了。"
    ]


async def collect_events(stream) -> list[dict[str, object]]:
    return [event async for event in stream]


def test_stream_completion_emits_trace_steps_before_answer_chunks() -> None:
    traces = FakeTraceRepository()
    service = build_service(
        traces=traces,
        llm_config=FakeLLMConfigRepository(enabled=False),
        llm_client=OpenAICompatibleLLMClient(),
    )

    events = asyncio.run(
        collect_events(
            service.stream_complete(
                message="P0a 要交付什么？",
                tenant_id="tenant-demo",
                user_id="user-demo",
            )
        )
    )

    event_names = [str(event["event"]) for event in events]
    assert event_names.count("trace_step") == 14
    assert event_names.index("trace_step") < event_names.index("message_delta")
    assert event_names.index("message_delta") < event_names.index("response_meta")
    assert event_names.index("response_meta") < event_names.index("message_done")
    assert event_names[-1] == "done"
    assert "".join(str(event["content"]) for event in events if event["event"] == "message_delta")
    assert traces.saved is not None


def test_dialogue_can_invoke_common_report_skill_and_json_path_tool() -> None:
    traces = FakeTraceRepository()
    service = build_service(
        traces=traces,
        llm_config=FakeLLMConfigRepository(enabled=False),
        llm_client=OpenAICompatibleLLMClient(),
    )

    response = asyncio.run(service.complete(message="汇总 P0a 交付报告", tenant_id="tenant-demo", user_id="user-demo"))

    assert response["intent"] == "report_compose"
    assert "通用报告 Skill" in response["message"]["content"]
    assert traces.saved is not None
    skill_step = next(step for step in traces.saved.steps if step.name == "skill_selected")
    tool_step = next(step for step in traces.saved.steps if step.name == "tool_executed")
    assert skill_step.ref == "report_compose"
    assert skill_step.ref_source == "_common"
    assert tool_step.ref == "json_path"
    assert tool_step.node_type == "tool"


def test_plain_general_question_does_not_search_knowledge() -> None:
    traces = FakeTraceRepository()
    llm_client = FakeLLMClient()
    service = build_service(
        traces=traces,
        llm_config=FakeLLMConfigRepository(enabled=True),
        llm_client=llm_client,
    )

    response = asyncio.run(service.complete(message="平台是什么？", tenant_id="tenant-demo", user_id="user-demo"))

    assert response["intent"] == "general_chat"
    assert traces.saved is not None
    assert all(step.ref != "kb_grounded_qa" for step in traces.saved.steps)


def test_explicit_document_question_uses_knowledge_skill() -> None:
    traces = FakeTraceRepository()
    service = build_service(
        traces=traces,
        llm_config=FakeLLMConfigRepository(enabled=False),
        llm_client=OpenAICompatibleLLMClient(),
    )

    response = asyncio.run(service.complete(message="根据文档回答 P0a 要交付什么？", tenant_id="tenant-demo", user_id="user-demo"))

    assert response["intent"] == "knowledge_query"
    assert traces.saved is not None
    skill_step = next(step for step in traces.saved.steps if step.name == "skill_selected")
    assert skill_step.ref == "kb_grounded_qa"


def test_dialogue_can_invoke_platform_time_tool() -> None:
    traces = FakeTraceRepository()
    llm_client = FakeLLMClient([
        '{"intent":"tool.time_now","action_type":"tool","action_name":"time_now","arguments":{"timezone":"Asia/Shanghai"},"reason":"用户询问当前时间"}'
    ])
    service = build_service(
        traces=traces,
        llm_config=FakeLLMConfigRepository(enabled=True),
        llm_client=llm_client,
    )

    response = asyncio.run(service.complete(message="当前时间是多少？", tenant_id="tenant-demo", user_id="user-demo"))

    assert response["intent"] == "tool.time_now"
    assert "当前时间" in response["message"]["content"]
    assert traces.saved is not None
    tool_step = next(step for step in traces.saved.steps if step.name == "tool_executed")
    assert tool_step.ref == "time_now"
    assert tool_step.node_type == "tool"


def test_dialogue_can_invoke_time_tool_with_natural_question() -> None:
    traces = FakeTraceRepository()
    llm_client = FakeLLMClient([
        '{"intent":"tool.time_now","action_type":"tool","action_name":"time_now","arguments":{"timezone":"Asia/Shanghai"},"reason":"用户询问当前时间"}'
    ])
    service = build_service(
        traces=traces,
        llm_config=FakeLLMConfigRepository(enabled=True),
        llm_client=llm_client,
    )

    response = asyncio.run(service.complete(message="我问你现在的时间是什么", tenant_id="tenant-demo", user_id="user-demo"))

    assert response["intent"] == "tool.time_now"
    assert "当前时间" in response["message"]["content"]
    assert traces.saved is not None
    planner_step = next(step for step in traces.saved.steps if step.name == "react_planner")
    assert planner_step.status == "completed"
    tool_step = next(step for step in traces.saved.steps if step.name == "tool_executed")
    assert tool_step.ref == "time_now"


def test_dialogue_can_invoke_time_tool_with_us_timezones() -> None:
    traces = FakeTraceRepository()
    llm_client = FakeLLMClient([
        '{"intent":"tool.time_now","action_type":"tool","action_name":"time_now","arguments":{"timezones":["America/New_York","America/Chicago","America/Denver","America/Los_Angeles"]},"reason":"用户询问美国时间，美国有多个主要时区"}'
    ])
    service = build_service(
        traces=traces,
        llm_config=FakeLLMConfigRepository(enabled=True),
        llm_client=llm_client,
    )

    response = asyncio.run(service.complete(message="美国时间是什么时间？", tenant_id="tenant-demo", user_id="user-demo"))

    assert response["intent"] == "tool.time_now"
    assert "America/New_York" in response["message"]["content"]
    assert "America/Los_Angeles" in response["message"]["content"]
    assert "Asia/Shanghai" not in response["message"]["content"]


def test_dialogue_can_invoke_platform_json_path_tool() -> None:
    traces = FakeTraceRepository()
    service = build_service(
        traces=traces,
        llm_config=FakeLLMConfigRepository(enabled=False),
        llm_client=OpenAICompatibleLLMClient(),
    )

    response = asyncio.run(
        service.complete(
            message='用 json_path $.items[0].name 查询 {"items":[{"name":"alpha"}]}',
            tenant_id="tenant-demo",
            user_id="user-demo",
        )
    )

    assert response["intent"] == "tool.json_path"
    assert "alpha" in response["message"]["content"]
    assert traces.saved is not None
    tool_step = next(step for step in traces.saved.steps if step.name == "tool_executed")
    assert tool_step.ref == "json_path"


def test_fault_diagnosis_plan_extracts_equipment_and_fault_code_from_message() -> None:
    traces = FakeTraceRepository()
    service = build_service(
        traces=traces,
        llm_config=FakeLLMConfigRepository(enabled=False),
        llm_client=OpenAICompatibleLLMClient(),
    )

    capability_name, payload = service._plan("3 号注塑机昨晚报 AX-203，怎么处理？", "fault_diagnosis")

    assert capability_name == "knowledge.search"
    assert payload["equipment_id"] == "3号注塑机"
    assert payload["fault_code"] == "AX-203"
    assert payload["last_n"] == 5
    assert payload["query"] == "3 号注塑机昨晚报 AX-203，怎么处理？"


def test_fault_diagnosis_chat_runs_declarative_skill_steps(monkeypatch) -> None:
    from agent_platform.runtime.skill_registry import SkillRegistry, ToolRegistry

    loader = MemoryPackageLoader([build_fault_triage_package()])
    monkeypatch.setattr(PackageLoader, "default", classmethod(lambda cls: loader))
    traces = FakeTraceRepository()
    service = build_service(
        traces=traces,
        llm_config=FakeLLMConfigRepository(enabled=False),
        llm_client=OpenAICompatibleLLMClient(),
    )
    service._registry = CapabilityRegistry(loader=loader)
    service._skills = SkillRegistry(loader=loader)
    service._tools = ToolRegistry()

    response = asyncio.run(
        service.complete(
            message="3 号注塑机昨晚报 AX-203，怎么处理？",
            tenant_id="tenant-demo",
            user_id="user-demo",
        )
    )

    assert response["intent"] == "fault_diagnosis"
    assert "已完成设备 3号注塑机 的故障排查编排" in response["message"]["content"]
    assert traces.saved is not None
    step_names = [step.name for step in traces.saved.steps]
    assert "skill_step:alarms" in step_names
    assert "skill_step:history" in step_names
    assert "skill_step:knowledge" in step_names
    skill_step = next(step for step in traces.saved.steps if step.name == "skill_selected")
    assert skill_step.ref == "fault_triage"
    executed_step = next(step for step in traces.saved.steps if step.name == "executed")
    assert executed_step.node_type == "skill"
    assert executed_step.ref == "fault_triage"
