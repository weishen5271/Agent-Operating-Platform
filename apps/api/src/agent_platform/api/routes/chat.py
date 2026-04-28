from __future__ import annotations

from dataclasses import asdict
import json
import logging
from typing import AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from agent_platform.api.deps import AuthContext
from agent_platform.api.schemas.chat import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ConversationListResponse,
    ConversationResponse,
    DraftActionRequest,
    DraftActionResponse,
    TraceResponse,
)
from agent_platform.bootstrap.container import chat_service

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger("agent_platform.api.chat")


def _sse(event: dict[str, object]) -> str:
    # 前端按 event 字段分流处理 Trace、增量文本和最终元数据；这里统一序列化 SSE 帧。
    name = str(event.get("event", "message"))
    return f"event: {name}\ndata: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


@router.post("/completions", response_model=ChatCompletionResponse)
async def create_completion(payload: ChatCompletionRequest, auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        # 同步接口仍复用 ChatService 主链路，避免和流式接口出现两套规划/治理逻辑。
        return await chat_service.complete(
            message=payload.message,
            conversation_id=payload.conversation_id,
            tenant_id=tenant_id,
            user_id=user_id,
            retrieval_mode=payload.retrieval_mode,
            primary_package=payload.primary_package,
            common_packages=payload.common_packages,
        )
    except PermissionError as exc:
        logger.warning(
            "Chat completion permission denied tenant=%s user=%s message=%r: %s",
            tenant_id,
            user_id,
            payload.message,
            exc,
        )
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        logger.warning(
            "Chat completion bad request tenant=%s user=%s message=%r: %s",
            tenant_id,
            user_id,
            payload.message,
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        logger.exception(
            "Chat completion failed tenant=%s user=%s message=%r",
            tenant_id,
            user_id,
            payload.message,
        )
        raise


@router.post("/completions/stream")
async def stream_completion(payload: ChatCompletionRequest, auth: AuthContext) -> StreamingResponse:
    tenant_id, user_id = auth

    async def events() -> AsyncIterator[str]:
        try:
            # 流式接口只负责把运行时事件转成 SSE，具体执行阶段仍由 ChatService 产生可审计 Trace。
            async for event in chat_service.stream_complete(
                message=payload.message,
                conversation_id=payload.conversation_id,
                tenant_id=tenant_id,
                user_id=user_id,
                retrieval_mode=payload.retrieval_mode,
                primary_package=payload.primary_package,
                common_packages=payload.common_packages,
            ):
                yield _sse(event)
        except PermissionError as exc:
            logger.warning(
                "Chat stream permission denied tenant=%s user=%s message=%r: %s",
                tenant_id,
                user_id,
                payload.message,
                exc,
            )
            yield _sse({"event": "error", "message": str(exc), "status": 403})
        except ValueError as exc:
            logger.warning(
                "Chat stream bad request tenant=%s user=%s message=%r: %s",
                tenant_id,
                user_id,
                payload.message,
                exc,
                exc_info=True,
            )
            yield _sse({"event": "error", "message": str(exc), "status": 400})
        except Exception as exc:
            logger.exception(
                "Chat stream failed tenant=%s user=%s message=%r",
                tenant_id,
                user_id,
                payload.message,
            )
            yield _sse({"event": "error", "message": f"{exc.__class__.__name__}: {exc}", "status": 500})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/conversations", response_model=ConversationListResponse)
async def list_conversations(auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    return {"items": await chat_service.list_conversations(tenant_id=tenant_id, user_id=user_id)}


@router.post("/conversations", response_model=ConversationResponse)
async def create_conversation(auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    conversation = await chat_service.create_conversation(tenant_id=tenant_id, user_id=user_id)
    return {**conversation, "messages": []}


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(conversation_id: str, auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    conversation = await chat_service.get_conversation(
        conversation_id=conversation_id,
        tenant_id=tenant_id,
        user_id=user_id,
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {
        "conversation_id": conversation.conversation_id,
        "title": conversation.title,
        "updated_at": conversation.updated_at,
        "messages": [
            {
                "role": message.role,
                "content": message.content,
                "created_at": message.created_at,
            }
            for message in conversation.messages
        ],
    }


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    deleted = await chat_service.delete_conversation(
        conversation_id=conversation_id,
        tenant_id=tenant_id,
        user_id=user_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"deleted": True}


@router.get("/traces/{trace_id}", response_model=TraceResponse)
async def get_trace(trace_id: str, auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    trace = await chat_service.get_trace(trace_id, tenant_id=tenant_id, user_id=user_id)
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
