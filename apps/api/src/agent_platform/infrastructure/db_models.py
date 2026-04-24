from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agent_platform.infrastructure.db import Base


class TenantRecord(Base):
    __tablename__ = "tenant"

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    package: Mapped[str] = mapped_column(String(255), nullable=False)
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    budget: Mapped[str] = mapped_column(String(64), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class UserAccountRecord(Base):
    __tablename__ = "user_account"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    document: Mapped["KnowledgeDocumentRecord"] = relationship(back_populates="chunks")


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
    source_id: Mapped[str] = mapped_column(ForeignKey("knowledge_document.source_id"), nullable=False, index=True)
    chunk_id: Mapped[str] = mapped_column(ForeignKey("knowledge_chunk.chunk_id"), nullable=False, index=True)
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

    knowledge_base_code: Mapped[str] = mapped_column(String(64), primary_key=True)
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
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


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
        KnowledgeWikiPageRecord,
        KnowledgeWikiPageRevisionRecord,
        KnowledgeWikiCitationRecord,
        KnowledgeWikiLinkRecord,
        KnowledgeWikiCompileRunRecord,
        KnowledgeWikiFeedbackRecord,
        KnowledgeBaseRecord,
        LLMRuntimeConfigRecord,
    )
