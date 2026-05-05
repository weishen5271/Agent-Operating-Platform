from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agent_platform.infrastructure.db import Base


class TenantRecord(Base):
    __tablename__ = "tenant"

    tenant_record_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    package: Mapped[str] = mapped_column(String(255), nullable=False)
    enabled_common_packages: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    budget: Mapped[str] = mapped_column(String(64), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class UserAccountRecord(Base):
    __tablename__ = "user_account"

    user_account_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.tenant_id"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ConversationRecord(Base):
    __tablename__ = "conversation"

    conversation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.tenant_id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    messages: Mapped[list["ConversationMessageRecord"]] = relationship(back_populates="conversation")


class ConversationMessageRecord(Base):
    __tablename__ = "conversation_message"

    message_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversation.conversation_id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    conversation: Mapped["ConversationRecord"] = relationship(back_populates="messages")


class RequestTraceRecord(Base):
    __tablename__ = "request_trace"

    trace_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.tenant_id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    intent: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, default="", nullable=False)
    sources: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    steps: Mapped[list["TraceStepRecord"]] = relationship(back_populates="trace")


class TraceStepRecord(Base):
    __tablename__ = "trace_step"

    step_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trace_id: Mapped[str] = mapped_column(ForeignKey("request_trace.trace_id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    node_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ref_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ref_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trace: Mapped["RequestTraceRecord"] = relationship(back_populates="steps")


class ApprovalRequestRecord(Base):
    __tablename__ = "approval_request"

    draft_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.tenant_id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    capability_name: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    approval_hint: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SecurityEventRecord(Base):
    __tablename__ = "security_event"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.tenant_id"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ToolOverrideRecord(Base):
    __tablename__ = "tool_override"

    override_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.tenant_id"), nullable=False, index=True)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    quota: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timeout: Mapped[int | None] = mapped_column(Integer, nullable=True)
    disabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class OutputGuardRuleRecord(Base):
    __tablename__ = "output_guard_rule"

    rule_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    package_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    pattern: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    source: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class PluginConfigRecord(Base):
    __tablename__ = "plugin_config"

    config_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.tenant_id"), nullable=False, index=True)
    plugin_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class McpServerRecord(Base):
    __tablename__ = "mcp_server"

    server_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    transport: Mapped[str] = mapped_column(String(64), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(1024), nullable=False)
    auth_ref: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    headers: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ReleasePlanRecord(Base):
    __tablename__ = "release_plan"

    release_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    package_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    package_name: Mapped[str] = mapped_column(String(255), nullable=False)
    skill: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    rollout_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metric_delta: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class KnowledgeDocumentRecord(Base):
    __tablename__ = "knowledge_document"

    source_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.tenant_id"), nullable=False, index=True)
    knowledge_base_code: Mapped[str] = mapped_column(String(64), nullable=False, default="knowledge", index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    chunk_attributes_schema: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    chunks: Mapped[list["KnowledgeChunkRecord"]] = relationship(back_populates="document")


class KnowledgeChunkRecord(Base):
    __tablename__ = "knowledge_chunk"

    chunk_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("knowledge_document.source_id"), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.tenant_id"), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    embedding: Mapped[list[float]] = mapped_column(JSON, default=list, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="published", index=True)
    embedding_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    embedding_model: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    document: Mapped["KnowledgeDocumentRecord"] = relationship(back_populates="chunks")


class KnowledgeWikiSourceRecord(Base):
    __tablename__ = "knowledge_wiki_source"

    source_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.tenant_id"), nullable=False, index=True)
    knowledge_base_code: Mapped[str] = mapped_column(String(64), nullable=False, default="knowledge", index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    chunk_attributes_schema: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    chunks: Mapped[list["KnowledgeWikiSourceChunkRecord"]] = relationship(back_populates="document")


class KnowledgeWikiSourceChunkRecord(Base):
    __tablename__ = "knowledge_wiki_source_chunk"

    chunk_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("knowledge_wiki_source.source_id"), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.tenant_id"), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    embedding: Mapped[list[float]] = mapped_column(JSON, default=list, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="published", index=True)
    embedding_status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    embedding_model: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    document: Mapped["KnowledgeWikiSourceRecord"] = relationship(back_populates="chunks")


class KnowledgeWikiPageRecord(Base):
    __tablename__ = "knowledge_wiki_page"

    page_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.tenant_id"), nullable=False, index=True)
    space_code: Mapped[str] = mapped_column(String(64), nullable=False, default="knowledge")
    page_type: Mapped[str] = mapped_column(String(32), nullable=False, default="overview")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    content_markdown: Mapped[str] = mapped_column(Text, default="", nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", index=True)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    freshness_score: Mapped[float] = mapped_column(nullable=False, default=0.0)
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    citation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    revision_no: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="system")
    updated_by: Mapped[str] = mapped_column(String(64), nullable=False, default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class KnowledgeWikiPageRevisionRecord(Base):
    __tablename__ = "knowledge_wiki_page_revision"

    revision_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    page_id: Mapped[str] = mapped_column(ForeignKey("knowledge_wiki_page.page_id"), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.tenant_id"), nullable=False, index=True)
    revision_no: Mapped[int] = mapped_column(Integer, nullable=False)
    compile_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("knowledge_wiki_compile_run.compile_run_id"),
        nullable=True,
        index=True,
    )
    change_type: Mapped[str] = mapped_column(String(32), nullable=False, default="update")
    content_markdown: Mapped[str] = mapped_column(Text, default="", nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    change_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    quality_score: Mapped[float] = mapped_column(nullable=False, default=0.0)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="system")


class KnowledgeWikiCitationRecord(Base):
    __tablename__ = "knowledge_wiki_citation"

    citation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.tenant_id"), nullable=False, index=True)
    page_id: Mapped[str] = mapped_column(ForeignKey("knowledge_wiki_page.page_id"), nullable=False, index=True)
    revision_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge_wiki_page_revision.revision_id"),
        nullable=False,
        index=True,
    )
    section_key: Mapped[str] = mapped_column(String(128), nullable=False)
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[str] = mapped_column(ForeignKey("knowledge_wiki_source.source_id"), nullable=False, index=True)
    chunk_id: Mapped[str] = mapped_column(ForeignKey("knowledge_wiki_source_chunk.chunk_id"), nullable=False, index=True)
    evidence_snippet: Mapped[str] = mapped_column(Text, default="", nullable=False)
    support_type: Mapped[str] = mapped_column(String(16), nullable=False, default="direct")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class KnowledgeWikiLinkRecord(Base):
    __tablename__ = "knowledge_wiki_link"

    link_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.tenant_id"), nullable=False, index=True)
    from_page_id: Mapped[str] = mapped_column(ForeignKey("knowledge_wiki_page.page_id"), nullable=False, index=True)
    to_page_id: Mapped[str] = mapped_column(ForeignKey("knowledge_wiki_page.page_id"), nullable=False, index=True)
    link_type: Mapped[str] = mapped_column(String(32), nullable=False, default="related")
    weight: Mapped[float] = mapped_column(nullable=False, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class KnowledgeWikiCompileRunRecord(Base):
    __tablename__ = "knowledge_wiki_compile_run"

    compile_run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.tenant_id"), nullable=False, index=True)
    trigger_type: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False, default="source")
    scope_value: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    input_source_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    input_chunk_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    affected_page_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    error_message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    token_usage: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class KnowledgeWikiFeedbackRecord(Base):
    __tablename__ = "knowledge_wiki_feedback"

    feedback_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.tenant_id"), nullable=False, index=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    page_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    result_status: Mapped[str] = mapped_column(String(32), nullable=False, default="partial")
    feedback_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class KnowledgeBaseRecord(Base):
    __tablename__ = "knowledge_base"

    knowledge_base_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    knowledge_base_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.tenant_id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    created_by: Mapped[str] = mapped_column(String(64), nullable=False, default="system")
    updated_by: Mapped[str] = mapped_column(String(64), nullable=False, default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class LLMRuntimeConfigRecord(Base):
    __tablename__ = "llm_runtime_config"

    config_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str | None] = mapped_column(ForeignKey("tenant.tenant_id"), nullable=True, index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    base_url: Mapped[str] = mapped_column(String(1024), default="", nullable=False)
    model: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    api_key: Mapped[str] = mapped_column(Text, default="", nullable=False)
    temperature: Mapped[float] = mapped_column(nullable=False, default=0.2)
    system_prompt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    embedding_provider: Mapped[str] = mapped_column(String(64), default="openai-compatible", nullable=False)
    embedding_base_url: Mapped[str] = mapped_column(String(1024), default="", nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    embedding_api_key: Mapped[str] = mapped_column(Text, default="", nullable=False)
    embedding_dimensions: Mapped[int] = mapped_column(Integer, default=1536, nullable=False)
    embedding_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class BusinessOutputRecord(Base):
    __tablename__ = "business_output"

    output_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.tenant_id"), nullable=False, index=True)
    package_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    citations: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    conversation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    action_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    object_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    object_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    linked_draft_group_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AIRunRecord(Base):
    __tablename__ = "ai_run"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.tenant_id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    package_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    action_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    object_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    object_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    inputs: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    data_input_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    output_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    draft_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # 时间类字段统一保存 Unix timestamp 毫秒，不在实体层混用 datetime / 字符串。
    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[int] = mapped_column(BigInteger, nullable=False)



def import_db_models() -> None:
    _ = (
        TenantRecord,
        UserAccountRecord,
        ConversationRecord,
        ConversationMessageRecord,
        RequestTraceRecord,
        TraceStepRecord,
        ApprovalRequestRecord,
        SecurityEventRecord,
        KnowledgeDocumentRecord,
        KnowledgeChunkRecord,
        KnowledgeWikiSourceRecord,
        KnowledgeWikiSourceChunkRecord,
        KnowledgeWikiPageRecord,
        KnowledgeWikiPageRevisionRecord,
        KnowledgeWikiCitationRecord,
        KnowledgeWikiLinkRecord,
        KnowledgeWikiCompileRunRecord,
        KnowledgeWikiFeedbackRecord,
        KnowledgeBaseRecord,
        LLMRuntimeConfigRecord,
        McpServerRecord,
        BusinessOutputRecord,
        AIRunRecord,
    )
