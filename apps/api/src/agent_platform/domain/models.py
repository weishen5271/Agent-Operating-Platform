from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class SourceReference:
    id: str
    title: str
    snippet: str
    source_type: str
    page_id: str | None = None
    revision_id: str | None = None
    citation_id: str | None = None
    claim_text: str | None = None
    source_id: str | None = None
    chunk_id: str | None = None
    locator: str | None = None
    # 完整 chunk 正文，仅用于喂给 LLM；snippet 仍用于 UI 显示。
    content: str | None = None


@dataclass(slots=True)
class TraceStep:
    name: str
    status: str
    summary: str
    timestamp: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class TraceRecord:
    trace_id: str
    tenant_id: str
    user_id: str
    message: str
    intent: str
    strategy: str
    answer: str = ""
    sources: list[SourceReference] = field(default_factory=list)
    steps: list[TraceStep] = field(default_factory=list)
    created_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class CapabilityDefinition:
    name: str
    description: str
    risk_level: str
    side_effect_level: str
    required_scope: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    enabled: bool = True


@dataclass(slots=True)
class ConversationMessage:
    role: str
    content: str
    created_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class Conversation:
    conversation_id: str
    title: str
    tenant_id: str
    user_id: str
    messages: list[ConversationMessage] = field(default_factory=list)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class TenantProfile:
    tenant_id: str
    name: str
    package: str
    environment: str
    budget: str
    active: bool = True


@dataclass(slots=True)
class UserContext:
    user_id: str
    tenant_id: str
    role: str
    scopes: list[str]
    email: str = ""


@dataclass(slots=True)
class DraftAction:
    draft_id: str
    tenant_id: str
    user_id: str
    capability_name: str
    title: str
    risk_level: str
    status: str
    payload: dict[str, Any]
    summary: str
    approval_hint: str
    created_at: datetime = field(default_factory=utc_now)
    confirmed_at: datetime | None = None


@dataclass(slots=True)
class SecurityEvent:
    event_id: str
    tenant_id: str
    category: str
    severity: str
    title: str
    status: str
    owner: str


@dataclass(slots=True)
class KnowledgeSource:
    source_id: str
    tenant_id: str
    knowledge_base_code: str
    name: str
    source_type: str
    owner: str
    chunk_count: int
    status: str


@dataclass(slots=True)
class KnowledgeChunk:
    chunk_id: str
    source_id: str
    tenant_id: str
    chunk_index: int
    title: str
    content: str
    content_hash: str
    metadata_json: dict[str, Any]
    token_count: int
    status: str
    created_at: datetime


@dataclass(slots=True)
class KnowledgeSourceDetail:
    source: KnowledgeSource
    chunks: list[KnowledgeChunk]
    content: str


@dataclass(slots=True)
class KnowledgeBase:
    knowledge_base_id: str
    knowledge_base_code: str
    tenant_id: str
    name: str
    description: str
    status: str
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class KnowledgeSearchResult:
    matches: list[SourceReference]
    backend: str
    query: str
    candidate_count: int
    match_count: int
    keyword_match_count: int
    vector_match_count: int


@dataclass(slots=True)
class LLMRuntimeConfig:
    provider: str
    base_url: str
    model: str
    api_key_configured: bool
    temperature: float
    system_prompt: str
    enabled: bool
    # Embedding 子配置：用于知识库向量化与 RAG 检索时的 query 编码。
    # 若 embedding_enabled=False 或 embedding_api_key 缺失，则系统退化为关键词匹配。
    embedding_provider: str = "openai-compatible"
    embedding_base_url: str = ""
    embedding_model: str = ""
    embedding_dimensions: int = 1536
    embedding_api_key_configured: bool = False
    embedding_enabled: bool = False
