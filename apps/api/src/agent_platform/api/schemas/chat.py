from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ChatCompletionRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = None
    tenant_id: str | None = None
    user_id: str | None = None


class ChatMessageResponse(BaseModel):
    role: str
    content: str


class SourceReferenceResponse(BaseModel):
    id: str
    title: str
    snippet: str
    source_type: str


class ChatCompletionResponse(BaseModel):
    trace_id: str
    conversation_id: str
    intent: str
    strategy: str
    message: ChatMessageResponse
    sources: list[SourceReferenceResponse]
    draft_action: dict | None = None


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
