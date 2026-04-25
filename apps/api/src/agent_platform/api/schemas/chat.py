from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ChatCompletionRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = None
    tenant_id: str | None = None
    user_id: str | None = None
    retrieval_mode: Literal["auto", "rag", "wiki"] = "auto"


class ChatMessageResponse(BaseModel):
    role: str
    content: str


class ConversationMessageResponse(ChatMessageResponse):
    created_at: datetime


class ConversationSummaryResponse(BaseModel):
    conversation_id: str
    title: str
    updated_at: datetime


class ConversationListResponse(BaseModel):
    items: list[ConversationSummaryResponse]


class ConversationResponse(ConversationSummaryResponse):
    messages: list[ConversationMessageResponse]


class SourceReferenceResponse(BaseModel):
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


class ChatCompletionResponse(BaseModel):
    trace_id: str
    conversation_id: str
    intent: str
    strategy: str
    message: ChatMessageResponse
    sources: list[SourceReferenceResponse]
    draft_action: dict | None = None
    warnings: list[str] = []


class TraceStepResponse(BaseModel):
    name: str
    status: str
    summary: str
    timestamp: datetime


class TraceResponse(BaseModel):
    trace_id: str
    tenant_id: str
    user_id: str
    message: str
    intent: str
    strategy: str
    answer: str
    steps: list[TraceStepResponse]
    sources: list[SourceReferenceResponse]
    created_at: datetime


class DraftActionRequest(BaseModel):
    capability_name: str
    payload: dict
    tenant_id: str | None = None
    user_id: str | None = None


class DraftActionResponse(BaseModel):
    draft_id: str
    title: str
    capability_name: str
    risk_level: str
    status: str
    summary: str
    approval_hint: str
    payload: dict
    created_at: datetime
