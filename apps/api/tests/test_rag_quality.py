"""P2 阶段回归用例：query 改写、rerank、空召回兜底。"""

from __future__ import annotations

import asyncio

from agent_platform.domain.models import (
    KnowledgeSearchResult,
    KnowledgeSource,
    LLMRuntimeConfig,
    SourceReference,
)
from agent_platform.runtime.chat_service import ChatService
from agent_platform.runtime.registry import CapabilityRegistry

from test_chat_runtime_chain import (
    FakeConversationRepository,
    FakeDraftRepository,
    FakeKnowledgeBaseRepository,
    FakeLLMConfigRepository,
    FakeSecurityRepository,
    FakeTenantRepository,
    FakeTraceRepository,
    FakeUserRepository,
    FakeWikiService,
)


class StubLLMClient:
    """记录调用并按预设脚本返回的 LLM 客户端。"""

    def __init__(self, scripted_responses: list[str]) -> None:
        self._responses = list(scripted_responses)
        self.calls: list[dict[str, object]] = []

    def complete(self, *, config, api_key: str, user_message: str, context_blocks: list[str]) -> str:
        self.calls.append(
            {
                "user_message": user_message,
                "context_blocks": list(context_blocks),
            }
        )
        if self._responses:
            return self._responses.pop(0)
        return "默认回复"


class RecordingKnowledgeRepo:
    """按 query 返回不同片段，便于检验多变体召回与 RRF 合并。"""

    def __init__(self, matches_by_query: dict[str, list[SourceReference]]) -> None:
        self._matches = matches_by_query
        self.queries: list[str] = []

    async def list_recent(self, tenant_id: str, knowledge_base_code: str | None = None):
        return [
            KnowledgeSource(
                source_id="ks-test",
                tenant_id=tenant_id,
                knowledge_base_code="default",
                name="测试知识库",
                source_type="Markdown",
                owner="知识平台组",
                chunk_count=1,
                status="运行中",
            )
        ]

    async def search(self, *, tenant_id: str, query: str, top_k: int = 3) -> KnowledgeSearchResult:
        self.queries.append(query)
        matches = self._matches.get(query, [])
        return KnowledgeSearchResult(
            matches=list(matches[:top_k]),
            backend="recording_hybrid",
            query=query,
            candidate_count=len(matches),
            match_count=min(len(matches), top_k),
            keyword_match_count=len(matches),
            vector_match_count=0,
        )


def _build_service(*, llm_client, knowledge_repo, llm_config: FakeLLMConfigRepository) -> ChatService:
    return ChatService(
        registry=CapabilityRegistry(),
        conversations=FakeConversationRepository(),
        traces=FakeTraceRepository(),
        tenants=FakeTenantRepository(),
        users=FakeUserRepository(),
        drafts=FakeDraftRepository(),
        security_events=FakeSecurityRepository(),
        knowledge_sources=knowledge_repo,
        knowledge_bases=FakeKnowledgeBaseRepository(),
        wiki_service=FakeWikiService(),
        llm_config=llm_config,
        llm_client=llm_client,
    )


def _enabled_config() -> LLMRuntimeConfig:
    return LLMRuntimeConfig(
        provider="openai-compatible",
        base_url="https://example.test/v1",
        model="test",
        api_key_configured=True,
        temperature=0.2,
        system_prompt="",
        enabled=True,
    )


# ---------- _rewrite_query ----------


def test_rewrite_query_parses_json_array() -> None:
    llm_client = StubLLMClient(['["可扩展 Agent 设计原则", "Agent 平台 模块划分"]'])
    service = _build_service(
        llm_client=llm_client,
        knowledge_repo=RecordingKnowledgeRepo({}),
        llm_config=FakeLLMConfigRepository(enabled=True),
    )

    variants = asyncio.run(
        service._rewrite_query(config=_enabled_config(), api_key="k", query="可扩展 Agent 架构如何设计")
    )

    assert variants == ["可扩展 Agent 设计原则", "Agent 平台 模块划分"]
    assert llm_client.calls and "JSON" in llm_client.calls[0]["user_message"]


def test_rewrite_query_returns_empty_when_llm_breaks() -> None:
    class BoomClient:
        def complete(self, **kwargs):
            raise ValueError("boom")

    service = _build_service(
        llm_client=BoomClient(),
        knowledge_repo=RecordingKnowledgeRepo({}),
        llm_config=FakeLLMConfigRepository(enabled=True),
    )

    variants = asyncio.run(
        service._rewrite_query(config=_enabled_config(), api_key="k", query="测试问题")
    )
    assert variants == []


def test_rewrite_query_handles_dirty_output_with_extra_text() -> None:
    llm_client = StubLLMClient(['这是变体: ["A", "B"] 仅供参考'])
    service = _build_service(
        llm_client=llm_client,
        knowledge_repo=RecordingKnowledgeRepo({}),
        llm_config=FakeLLMConfigRepository(enabled=True),
    )
    variants = asyncio.run(
        service._rewrite_query(config=_enabled_config(), api_key="k", query="如何设计")
    )
    assert variants == ["A", "B"]


# ---------- _rerank_candidates ----------


def _make_source(idx: int) -> SourceReference:
    return SourceReference(
        id=f"kc-{idx}",
        title=f"片段{idx}",
        snippet=f"内容{idx}",
        source_type="knowledge",
    )


def test_rerank_candidates_orders_by_score_and_drops_low_scores() -> None:
    candidates = [_make_source(i) for i in range(1, 6)]
    response = (
        '[{"index": 1, "score": 1}, {"index": 2, "score": 5}, '
        '{"index": 3, "score": 3}, {"index": 4, "score": 4}, {"index": 5, "score": 2}]'
    )
    llm_client = StubLLMClient([response])
    service = _build_service(
        llm_client=llm_client,
        knowledge_repo=RecordingKnowledgeRepo({}),
        llm_config=FakeLLMConfigRepository(enabled=True),
    )

    reranked = asyncio.run(
        service._rerank_candidates(
            config=_enabled_config(), api_key="k", query="测试", candidates=candidates
        )
    )

    assert reranked is not None
    # score 1 的片段被剔除；其余按 5,4,3,2 排序
    assert [item.id for item in reranked] == ["kc-2", "kc-4", "kc-3", "kc-5"]


def test_rerank_candidates_returns_none_on_invalid_output() -> None:
    candidates = [_make_source(i) for i in range(1, 4)]
    llm_client = StubLLMClient(["这是无效 JSON"])
    service = _build_service(
        llm_client=llm_client,
        knowledge_repo=RecordingKnowledgeRepo({}),
        llm_config=FakeLLMConfigRepository(enabled=True),
    )
    reranked = asyncio.run(
        service._rerank_candidates(
            config=_enabled_config(), api_key="k", query="测试", candidates=candidates
        )
    )
    assert reranked is None


# ---------- _run_knowledge_search 集成 ----------


def test_run_knowledge_search_fans_out_to_variants_and_reranks() -> None:
    matches_a = [_make_source(i) for i in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]]
    matches_b = [_make_source(i) for i in [10, 9, 8, 7, 11, 12]]
    knowledge_repo = RecordingKnowledgeRepo(
        {
            "原始问题": matches_a,
            "变体一": matches_b,
        }
    )

    rewrite_response = '["变体一"]'
    rerank_response = "[" + ", ".join(
        f'{{"index": {i}, "score": 5}}' for i in range(1, 9)
    ) + "]"
    llm_client = StubLLMClient([rewrite_response, rerank_response])

    service = _build_service(
        llm_client=llm_client,
        knowledge_repo=knowledge_repo,
        llm_config=FakeLLMConfigRepository(enabled=True),
    )

    result = asyncio.run(
        service._run_knowledge_search("tenant-demo", "原始问题")
    )

    # 应该向 repo 发起 2 次检索（原始 + 变体）
    assert knowledge_repo.queries == ["原始问题", "变体一"]
    retrieval = result["retrieval"]
    assert retrieval["variants"] == ["原始问题", "变体一"]
    assert retrieval["rerank_applied"] is True
    assert retrieval["match_count"] == 8
    # rerank 后保留了 top 8，且包含两路共享的高位文档
    ids = [item.id for item in result["matches"]]
    assert "kc-10" in ids and "kc-1" in ids


def test_run_knowledge_search_skips_rewrite_when_llm_disabled() -> None:
    matches = [_make_source(i) for i in range(1, 4)]
    knowledge_repo = RecordingKnowledgeRepo({"P0a 要交付什么？": matches})
    service = _build_service(
        llm_client=StubLLMClient([]),
        knowledge_repo=knowledge_repo,
        llm_config=FakeLLMConfigRepository(enabled=False),
    )

    result = asyncio.run(service._run_knowledge_search("tenant-demo", "P0a 要交付什么？"))

    assert knowledge_repo.queries == ["P0a 要交付什么？"]
    assert result["retrieval"]["variants"] == ["P0a 要交付什么？"]
    assert result["retrieval"]["rerank_applied"] is False


# ---------- 空召回兜底 ----------


def test_empty_recall_triggers_fallback_prompt_with_llm_enabled() -> None:
    llm_client = StubLLMClient(["目前知识库未收录直接相关资料。建议……"])
    service = _build_service(
        llm_client=llm_client,
        knowledge_repo=RecordingKnowledgeRepo({}),
        llm_config=FakeLLMConfigRepository(enabled=True),
    )

    from agent_platform.domain.models import Conversation

    answer = asyncio.run(
        service._generate_rag_llm_answer(
            tenant_id="tenant-demo",
            message="某个完全没收录的问题",
            sources=[],
            short_memory=Conversation(
                conversation_id="", title="t", tenant_id="tenant-demo", user_id="user-demo"
            ),
        )
    )

    assert answer == "目前知识库未收录直接相关资料。建议……"
    assert llm_client.calls
    blocks = llm_client.calls[0]["context_blocks"]
    assert any("空召回提示" in block for block in blocks)
