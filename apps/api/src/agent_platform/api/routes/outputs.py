from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from agent_platform.api.deps import AuthContext
from agent_platform.bootstrap.container import chat_service


router = APIRouter(prefix="/outputs", tags=["outputs"])


class CreateOutputRequest(BaseModel):
    type: str = Field(..., min_length=1, max_length=32)
    title: str = Field(..., min_length=1, max_length=255)
    package_id: str = Field(..., min_length=1, max_length=255)
    payload: dict[str, object] = Field(default_factory=dict)
    citations: list[str] = Field(default_factory=list)
    conversation_id: str | None = Field(default=None, max_length=64)
    trace_id: str | None = Field(default=None, max_length=64)
    summary: str = Field(default="")


class UpdateOutputRequest(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    status: str | None = Field(default=None, max_length=32)
    payload: dict[str, object] | None = Field(default=None)
    citations: list[str] | None = Field(default=None)
    summary: str | None = Field(default=None)
    linked_draft_group_id: str | None = Field(default=None, max_length=64)


@router.get("")
async def list_outputs(
    auth: AuthContext,
    type: str | None = Query(default=None, max_length=32),
    package: str | None = Query(default=None, max_length=255),
    status: str | None = Query(default=None, max_length=32),
) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await chat_service.list_business_outputs(
            tenant_id=tenant_id,
            user_id=user_id,
            type_filter=type,
            package_id=package,
            status=status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("")
async def create_output(payload: CreateOutputRequest, auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await chat_service.create_business_output(
            tenant_id=tenant_id,
            user_id=user_id,
            type=payload.type,
            title=payload.title,
            package_id=payload.package_id,
            payload=payload.payload,
            citations=payload.citations,
            conversation_id=payload.conversation_id,
            trace_id=payload.trace_id,
            summary=payload.summary,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{output_id}")
async def get_output(output_id: str, auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await chat_service.get_business_output(
            output_id, tenant_id=tenant_id, user_id=user_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{output_id}")
async def update_output(
    output_id: str, payload: UpdateOutputRequest, auth: AuthContext
) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await chat_service.update_business_output(
            output_id,
            tenant_id=tenant_id,
            user_id=user_id,
            title=payload.title,
            status=payload.status,
            payload=payload.payload,
            citations=payload.citations,
            summary=payload.summary,
            linked_draft_group_id=payload.linked_draft_group_id,
        )
    except ValueError as exc:
        status_code = 404 if "not found" in str(exc).lower() else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
