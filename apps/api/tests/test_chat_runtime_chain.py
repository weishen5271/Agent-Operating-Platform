import asyncio

from agent_platform.domain.models import (
    Conversation,
    ConversationMessage,
    KnowledgeSearchResult,
    KnowledgeSource,
    LLMRuntimeConfig,
    SourceReference,
    TenantProfile,
    UserContext,
)
from agent_platform.infrastructure.llm_client import OpenAICompatibleLLMClient
from agent_platform.runtime.chat_service import ChatService
from agent_platform.runtime.registry import CapabilityRegistry


class FakeConversationRepository:
    def __init__(self, conversation: Conversation | None = None) -> None:
        self.conversation = conversation

    async def list_recent(self, tenant_id: str, user_id: str, limit: int = 5) -> list[Conversation]:
        return [self.conversation] if self.conversation else []

    async def get(self, tenant_id: str, user_id: str, conversation_id: str) -> Conversation | None:
        if self.conversation and self.conversation.conversation_id == conversation_id:
            return self.conversation
        return None

    async def append_message(
        self,
        tenant_id: str,
        user_id: str,
        conversation_id: str | None,
        user_message: str,
        assistant_message: str,
    ) -> Conversation:
        return Conversation(
            conversation_id=conversation_id or "conv-test",
            title=user_message,
            tenant_id=tenant_id,
            user_id=user_id,
        )


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
    pass


class FakeKnowledgeBaseRepository:
    async def list_recent(self, tenant_id: str) -> list:
        return []


class FakeWikiService:
    async def search(self, *, query: str, tenant_id: str, user_id: str, top_k: int = 3, scope_mode: str = "chat"):
        return {"summary": "未启用 Wiki", "hits": []}


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


def build_service(
    *,
    traces: FakeTraceRepository,
    llm_config: FakeLLMConfigRepository,
    llm_client,
    conversations: FakeConversationRepository | None = None,
) -> ChatService:
    return ChatService(
        registry=CapabilityRegistry(),
        conversations=conversations or FakeConversationRepository(),
        traces=traces,
        tenants=FakeTenantRepository(),
        users=FakeUserRepository(),
        drafts=FakeDraftRepository(),
        security_events=FakeSecurityRepository(),
        knowledge_sources=FakeKnowledgeRepository(),
        knowledge_bases=FakeKnowledgeBaseRepository(),
        wiki_service=FakeWikiService(),
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
    # LLM 未启用且检索命中时，应给出退化提示
    assert "warnings" in response
    assert any("LLM" in tip for tip in response["warnings"])
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
    assert response["warnings"] == []
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
    assert llm_client.calls[0]["context_blocks"] == [
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
    assert event_names.count("trace_step") == 12
    assert event_names.index("trace_step") < event_names.index("message_delta")
    assert event_names.index("message_delta") < event_names.index("response_meta")
    assert event_names.index("response_meta") < event_names.index("message_done")
    assert event_names[-1] == "done"
    assert "".join(str(event["content"]) for event in events if event["event"] == "message_delta")
    assert traces.saved is not None
