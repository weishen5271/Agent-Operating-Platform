import asyncio

from agent_platform.domain.models import (
    Conversation,
    KnowledgeSource,
    LLMRuntimeConfig,
    TenantProfile,
    UserContext,
)
from agent_platform.infrastructure.llm_client import OpenAICompatibleLLMClient
from agent_platform.runtime.chat_service import ChatService
from agent_platform.runtime.registry import CapabilityRegistry


class FakeConversationRepository:
    async def list_recent(self, tenant_id: str, limit: int = 5) -> list[Conversation]:
        return []

    async def get(self, tenant_id: str, conversation_id: str) -> Conversation | None:
        return None

    async def append_message(
        self,
        tenant_id: str,
        conversation_id: str | None,
        user_message: str,
        assistant_message: str,
    ) -> Conversation:
        return Conversation(conversation_id=conversation_id or "conv-test", title=user_message, tenant_id=tenant_id)


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
                name="企业制度库",
                source_type="Markdown",
                owner="知识平台组",
                chunk_count=1,
                status="运行中",
            )
        ]


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
    pass


class FakeLLMClient:
    def __init__(self) -> None:
        self.calls = []

    def complete(self, *, config, api_key: str, user_message: str, context_blocks: list[str]) -> str:
        self.calls.append(
            {
                "model": config.model,
                "api_key": api_key,
                "user_message": user_message,
                "context_blocks": context_blocks,
            }
        )
        return f"模型回复：{user_message}"


def build_service(*, traces: FakeTraceRepository, llm_config: FakeLLMConfigRepository, llm_client) -> ChatService:
    return ChatService(
        registry=CapabilityRegistry(),
        conversations=FakeConversationRepository(),
        traces=traces,
        tenants=FakeTenantRepository(),
        users=FakeUserRepository(),
        drafts=FakeDraftRepository(),
        security_events=FakeSecurityRepository(),
        knowledge_sources=FakeKnowledgeRepository(),
        llm_config=llm_config,
        llm_client=llm_client,
    )


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
    assert traces.saved is not None
    step_names = [step.name for step in traces.saved.steps]
    assert step_names == [
        "received",
        "input_guard",
        "memory",
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
    assert response["message"]["content"] == "模型回复：你好，帮我解释一下你能做什么"
    assert llm_client.calls == [
        {
            "model": "test-model",
            "api_key": "test-key",
            "user_message": "你好，帮我解释一下你能做什么",
            "context_blocks": [],
        }
    ]
    assert llm_config.tenant_ids == ["tenant-demo"]
    assert traces.saved is not None
    assert [step.name for step in traces.saved.steps] == [
        "received",
        "input_guard",
        "memory",
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
