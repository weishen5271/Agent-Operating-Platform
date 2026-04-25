from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from agent_platform.api.deps import AuthContext
from agent_platform.api.schemas.chat import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    DraftActionRequest,
    DraftActionResponse,
    TraceResponse,
)
from agent_platform.bootstrap.container import chat_service

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/completions", response_model=ChatCompletionResponse)
async def create_completion(payload: ChatCompletionRequest, auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await chat_service.complete(
            message=payload.message,
            conversation_id=payload.conversation_id,
            tenant_id=tenant_id,
            user_id=user_id,
            retrieval_mode=payload.retrieval_mode,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/traces/{trace_id}", response_model=TraceResponse)
async def get_trace(trace_id: str) -> dict[str, object]:
    trace = await chat_service.get_trace(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    return {
        "trace_id": trace.trace_id,
        "tenant_id": trace.tenant_id,
        "user_id": trace.user_id,
        "message": trace.message,
        "intent": trace.intent,
        "strategy": trace.strategy,
        "answer": trace.answer,
        "steps": [asdict(step) for step in trace.steps],
        "sources": [asdict(source) for source in trace.sources],
        "created_at": trace.created_at,
    }


@router.post("/actions/draft", response_model=DraftActionResponse)
async def create_draft(payload: DraftActionRequest, auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        draft = await chat_service.create_draft(
            capability_name=payload.capability_name,
            payload=payload.payload,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        return chat_service._serialize_draft(draft)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/actions/{draft_id}/confirm", response_model=DraftActionResponse)
async def confirm_draft(draft_id: str, auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await chat_service.confirm_draft(draft_id=draft_id, tenant_id=tenant_id, user_id=user_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
