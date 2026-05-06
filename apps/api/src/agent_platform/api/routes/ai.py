from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from agent_platform.api.deps import AuthContext
from agent_platform.bootstrap.container import ai_run_service
from agent_platform.runtime.data_input import DataInput


router = APIRouter(prefix="/ai", tags=["ai"])


class DataInputRequest(BaseModel):
    """AI Action 的数据输入来源，Phase 1 默认平台主动查询外部系统。"""

    mode: str = Field(
        default="platform_pull",
        description="数据输入模式：platform_pull 表示平台按需查询外部系统，host_context 表示宿主传入上下文，mixed 表示两者混合。",
    )
    context: dict[str, object] = Field(
        default_factory=dict,
        description="本次执行携带的宿主上下文或补充输入。Phase 1 默认为空，不作为长期业务主数据保存。",
    )


class AIActionObjectRequest(BaseModel):
    object_type: str = Field(..., min_length=1, max_length=64, description="业务对象类型，例如 equipment。")
    object_id: str = Field(..., min_length=1, max_length=255, description="外部业务系统中的对象 ID，例如 CNC-01。")


class AIActionRunRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    package_id: str = Field(..., min_length=1, max_length=255, description="业务包 ID，例如 industry.mfg_maintenance。")
    source: str = Field(default="workspace", max_length=32, description="调用来源：workspace、chat、embed 或 api。")
    business_object: AIActionObjectRequest = Field(
        ...,
        alias="object",
        description="本次 AI 动作围绕的外部业务对象引用。",
    )
    inputs: dict[str, object] = Field(default_factory=dict, description="AI 动作参数，例如 fault_code、last_n、query。")
    data_input: DataInputRequest = Field(default_factory=DataInputRequest, description="本次执行的数据输入来源声明。")


class BusinessObjectLookupRequest(BaseModel):
    package_id: str = Field(..., min_length=1, max_length=255, description="业务包 ID，例如 industry.mfg_maintenance。")
    object_type: str = Field(..., min_length=1, max_length=64, description="业务对象类型，例如 equipment。")
    object_id: str = Field(..., min_length=1, max_length=255, description="外部业务对象 ID，例如 EQ-CNC-650-01。")


@router.get("/actions", summary="查询 AI 动作列表", description="按业务包查询 manifest 声明的结构化 AI 动作。")
async def list_actions(
    auth: AuthContext,
    package_id: str | None = Query(default=None, description="可选业务包 ID；为空时返回所有业务包的 AI 动作。"),
) -> dict[str, object]:
    tenant_id, user_id = auth
    return await ai_run_service.list_actions(tenant_id=tenant_id, user_id=user_id, package_id=package_id)


@router.get(
    "/business-objects",
    summary="查询业务对象声明",
    description="按业务包查询 manifest 声明的业务对象及其 lookup capability。",
)
async def list_business_objects(
    auth: AuthContext,
    package_id: str | None = Query(default=None, description="可选业务包 ID；为空时返回所有业务包的业务对象声明。"),
) -> dict[str, object]:
    tenant_id, user_id = auth
    return await ai_run_service.list_business_objects(tenant_id=tenant_id, user_id=user_id, package_id=package_id)


@router.post(
    "/business-objects/lookup",
    summary="查询业务对象",
    description="使用业务包声明的只读 lookup capability 查询外部业务对象，常用于执行 AI 动作前校验对象 ID。",
)
async def lookup_business_object(payload: BusinessObjectLookupRequest, auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await ai_run_service.lookup_business_object(
            tenant_id=tenant_id,
            user_id=user_id,
            package_id=payload.package_id,
            object_type=payload.object_type,
            object_id=payload.object_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Lookup capability not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post(
    "/actions/{action_id}/run",
    summary="执行 AI 动作",
    description="围绕指定业务对象执行结构化 AI 动作，并生成 AI Run、Trace 和 BusinessOutput。",
)
async def run_action(
    action_id: str,
    payload: AIActionRunRequest,
    auth: AuthContext,
) -> dict[str, object]:
    tenant_id, user_id = auth
    return await ai_run_service.run_action(
        tenant_id=tenant_id,
        user_id=user_id,
        package_id=payload.package_id,
        action_id=action_id,
        source=payload.source,
        object_type=payload.business_object.object_type,
        object_id=payload.business_object.object_id,
        inputs=payload.inputs,
        data_input=DataInput(mode=payload.data_input.mode, context=payload.data_input.context),
    )


@router.get("/runs", summary="查询 AI Run 列表", description="查询当前租户最近的结构化 AI 动作执行记录。")
async def list_runs(
    auth: AuthContext,
    limit: int = Query(default=20, ge=1, le=100, description="返回最近 AI Run 的数量。"),
) -> dict[str, object]:
    tenant_id, user_id = auth
    return await ai_run_service.list_runs(tenant_id=tenant_id, user_id=user_id, limit=limit)


@router.get("/runs/{run_id}", summary="查询 AI Run 详情", description="根据 run_id 查询一次 AI 动作执行记录。")
async def get_run(run_id: str, auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await ai_run_service.get_run(tenant_id=tenant_id, user_id=user_id, run_id=run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/runs/{run_id}/trace",
    summary="查询 AI Run Trace",
    description="根据 run_id 查询本次 AI 动作执行对应的 Trace 审计链路。",
)
async def get_run_trace(run_id: str, auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    try:
        return await ai_run_service.get_run_trace(tenant_id=tenant_id, user_id=user_id, run_id=run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
