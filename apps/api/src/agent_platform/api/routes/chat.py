from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Header, HTTPException

from agent_platform.api.schemas.chat import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    DraftActionRequest,
    DraftActionResponse,
    TraceResponse,
)
from agent_platform.bootstrap.container import chat_service
from agent_platform.infrastructure.auth import decode_access_token

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/completions", response_model=ChatCompletionResponse)
async def create_completion(
    payload: ChatCompletionRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    try:
        tenant_id, user_id = _resolve_request_context(
            authorization=authorization,
            tenant_id=payload.tenant_id,
            user_id=payload.user_id,
        )
        return await chat_service.complete(
            message=payload.message,
            conversation_id=payload.conversation_id,
            tenant_id=tenant_id,
            user_id=user_id,
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
async def create_draft(payload: DraftActionRequest) -> dict[str, object]:
    try:
        draft = await chat_service.create_draft(
            capability_name=payload.capability_name,
            payload=payload.payload,
            tenant_id=payload.tenant_id,
            user_id=payload.user_id,
        )
        return chat_service._serialize_draft(draft)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _resolve_request_context(
    *,
    authorization: str | None,
    tenant_id: str | None,
    user_id: str | None,
) -> tuple[str | None, str | None]:
    if not authorization:
        return tenant_id, user_id

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="认证令牌格式无效")

    payload = decode_access_token(authorization.removeprefix("Bearer ").strip())
    if payload is None:
        raise HTTPException(status_code=401, detail="认证令牌无效或已过期")

    token_user_id = payload.get("sub")
    token_tenant_id = payload.get("tenant_id")
    if not token_user_id or not token_tenant_id:
        raise HTTPException(status_code=401, detail="认证令牌缺少用户上下文")

    return token_tenant_id, token_user_id


@router.post("/actions/{draft_id}/confirm", response_model=DraftActionResponse)
async def confirm_draft(draft_id: str, tenant_id: str | None = None, user_id: str | None = None) -> dict[str, object]:
    try:
        return await chat_service.confirm_draft(draft_id=draft_id, tenant_id=tenant_id, user_id=user_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
