from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


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


TraceNodeType = Literal["capability", "tool", "skill", "retrieval", "guard", "runtime"]
TraceNodeSource = Literal["package", "_platform", "_common"]


@dataclass(slots=True)
class TraceStep:
    name: str
    status: str
    summary: str
    timestamp: datetime = field(default_factory=utc_now)
    # 节点分类，前端按类型选择图标 / 折叠策略；不填默认按 name 推断为 runtime。
    node_type: str | None = None
    # 引用对象名称，例如 capability="eam.workorder.draft.create"、skill="kb_grounded_qa"。
    ref: str | None = None
    # 引用来源：业务包 / 平台 / 通用包。
    ref_source: str | None = None
    ref_version: str | None = None
    duration_ms: int | None = None


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
    source: str = "_platform"
    package_id: str | None = None


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
    enabled_common_packages: list[str] = field(default_factory=list)
    active: bool = True

    @property
    def primary_package(self) -> str:
        return self.package


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
    chunk_attributes_schema: dict[str, Any] = field(default_factory=dict)


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


@dataclass(slots=True)
class ToolDefinition:
    """平台原子工具：无业务规则、无外部副作用，由后端代码实现。"""

    name: str
    description: str
    version: str
    source: str  # "_platform"
    timeout_ms: int = 5000
    quota_per_minute: int = 60
    enabled: bool = True


@dataclass(slots=True)
class ToolOverride:
    tenant_id: str
    tool_name: str
    quota: int | None = None
    timeout: int | None = None
    disabled: bool = False


@dataclass(slots=True)
class OutputGuardRule:
    rule_id: str
    package_id: str
    pattern: str
    action: str
    source: str
    enabled: bool = True


@dataclass(slots=True)
class PluginConfig:
    tenant_id: str
    plugin_name: str
    config: dict[str, Any]


@dataclass(slots=True)
class McpServer:
    server_id: str
    name: str
    transport: str
    endpoint: str
    auth_ref: str = ""
    headers: dict[str, Any] = field(default_factory=dict)
    status: str = "active"


@dataclass(slots=True)
class ReleasePlan:
    release_id: str
    package_id: str
    package_name: str
    skill: str
    version: str
    status: str
    rollout_percent: int
    metric_delta: str
    started_at: datetime


@dataclass(slots=True)
class SkillDefinition:
    """多步编排的技能：可以组合 Capability + Tool + 检索。"""

    name: str
    description: str
    version: str
    source: str  # "_platform" | "_common" | "package"
    package_id: str | None = None
    intents: list[str] = field(default_factory=list)
    depends_on_capabilities: list[str] = field(default_factory=list)
    depends_on_tools: list[str] = field(default_factory=list)
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    steps: list[dict[str, Any]] = field(default_factory=list)
    outputs_mapping: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True


@dataclass(slots=True)
class PackageDependency:
    kind: str  # "platform_skill" | "common_package" | "plugin" | "platform_tool"
    name: str
    version_range: str
    current_version: str
    compatible: bool = True


@dataclass(slots=True)
class RoutingDecision:
    matched_package_id: str
    confidence: float
    candidates: list[dict[str, Any]] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)


BusinessOutputType = Literal["report", "chart", "recommendation", "action_plan"]
BusinessOutputStatus = Literal["draft", "reviewing", "approved", "exported", "archived"]


@dataclass(slots=True)
class BusinessOutput:
    output_id: str
    tenant_id: str
    package_id: str
    type: str  # BusinessOutputType
    title: str
    status: str = "draft"  # BusinessOutputStatus
    payload: dict[str, Any] = field(default_factory=dict)
    citations: list[str] = field(default_factory=list)
    conversation_id: str | None = None
    trace_id: str | None = None
    linked_draft_group_id: str | None = None
    summary: str = ""
    created_by: str = ""
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
