from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from agent_platform.api.deps import AuthContext
from agent_platform.bootstrap.container import ai_run_service
from agent_platform.runtime.data_input import DataInput


router = APIRouter(prefix="/ai", tags=["ai"])


class DataInputRequest(BaseModel):
    """AI Action 的数据输入来源，Phase 1 默认平台主动查询外部系统。"""

    mode: str = "platform_pull"
    context: dict[str, object] = Field(default_factory=dict)


class AIActionObjectRequest(BaseModel):
    object_type: str = Field(..., min_length=1, max_length=64)
    object_id: str = Field(..., min_length=1, max_length=255)


class AIActionRunRequest(BaseModel):
    package_id: str = Field(..., min_length=1, max_length=255)
    source: str = Field(default="workspace", max_length=32)
    object: AIActionObjectRequest
    inputs: dict[str, object] = Field(default_factory=dict)
    data_input: DataInputRequest = Field(default_factory=DataInputRequest)


@router.get("/actions")
async def list_actions(auth: AuthContext, package_id: str | None = None) -> dict[str, object]:
    tenant_id, user_id = auth
    return await ai_run_service.list_actions(tenant_id=tenant_id, user_id=user_id, package_id=package_id)


@router.post("/actions/{action_id}/run")
async def run_action(action_id: str, payload: AIActionRunRequest, auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    return await ai_run_service.run_action(
        tenant_id=tenant_id,
        user_id=user_id,
        package_id=payload.package_id,
        action_id=action_id,
        source=payload.source,
        object_type=payload.object.object_type,
        object_id=payload.object.object_id,
        inputs=payload.inputs,
        data_input=DataInput(mode=payload.data_input.mode, context=payload.data_input.context),
    )


@router.get("/runs")
async def list_runs(
    auth: AuthContext,
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, object]:
    tenant_id, user_id = auth
    return await ai_run_service.list_runs(tenant_id=tenant_id, user_id=user_id, limit=limit)


@router.get("/runs/{run_id}")
async def get_run(run_id: str, auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await ai_run_service.get_run(tenant_id=tenant_id, user_id=user_id, run_id=run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs/{run_id}/trace")
async def get_run_trace(run_id: str, auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await ai_run_service.get_run_trace(tenant_id=tenant_id, user_id=user_id, run_id=run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
