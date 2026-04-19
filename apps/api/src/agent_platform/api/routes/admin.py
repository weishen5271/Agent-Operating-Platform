from __future__ import annotations

from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from agent_platform.bootstrap.container import chat_service

router = APIRouter(prefix="/admin", tags=["admin"])


class LLMRuntimeUpdateRequest(BaseModel):
    tenant_id: str | None = Field(default=None)
    provider: Literal["openai-compatible", "openai", "azure", "anthropic"] = Field(default="openai-compatible")
    base_url: str = Field(default="")
    model: str = Field(default="")
    api_key: str = Field(default="")
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    system_prompt: str = Field(default="")


class TenantCreateRequest(BaseModel):
    tenant_id: str = Field(..., max_length=64)
    name: str = Field(..., max_length=255)
    package: str = Field(..., max_length=255)
    environment: str = Field(..., max_length=64)
    budget: str = Field(..., max_length=64)


class TenantUpdateRequest(BaseModel):
    name: str = Field(..., max_length=255)
    package: str = Field(..., max_length=255)
    environment: str = Field(..., max_length=64)
    budget: str = Field(..., max_length=64)
    active: bool = Field(default=True)


class UserCreateRequest(BaseModel):
    user_id: str = Field(..., max_length=64)
    role: str = Field(..., max_length=64)
    scopes: list[str] = Field(default_factory=list)


class UserUpdateRequest(BaseModel):
    role: str = Field(..., max_length=64)
    scopes: list[str] = Field(default_factory=list)


@router.get("/packages")
async def list_packages(
    tenant_id: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
) -> dict[str, object]:
    try:
        return await chat_service.list_admin_packages(tenant_id=tenant_id, user_id=user_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/system")
async def system_overview(
    tenant_id: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
) -> dict[str, object]:
    try:
        return await chat_service.list_system_overview(tenant_id=tenant_id, user_id=user_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/llm-runtime")
async def llm_runtime(tenant_id: str | None = Query(default=None)) -> dict[str, object]:
    return await chat_service.get_llm_runtime(tenant_id=tenant_id)


@router.post("/llm-runtime")
async def update_llm_runtime(payload: LLMRuntimeUpdateRequest) -> dict[str, object]:
    return await chat_service.update_llm_runtime(
        tenant_id=payload.tenant_id,
        provider=payload.provider,
        base_url=payload.base_url,
        model=payload.model,
        api_key=payload.api_key,
        temperature=payload.temperature,
        system_prompt=payload.system_prompt,
    )


# Tenant CRUD
@router.get("/tenants")
async def list_tenants() -> dict[str, object]:
    return await chat_service.list_system_overview()


@router.post("/tenants")
async def create_tenant(payload: TenantCreateRequest) -> dict[str, object]:
    try:
        tenant = await chat_service.create_tenant(
            tenant_id=payload.tenant_id,
            name=payload.name,
            package=payload.package,
            environment=payload.environment,
            budget=payload.budget,
        )
        return asdict(tenant)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/tenants/{tenant_id}")
async def update_tenant(tenant_id: str, payload: TenantUpdateRequest) -> dict[str, object]:
    try:
        tenant = await chat_service.update_tenant(
            tenant_id=tenant_id,
            name=payload.name,
            package=payload.package,
            environment=payload.environment,
            budget=payload.budget,
            active=payload.active,
        )
        return asdict(tenant)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/tenants/{tenant_id}")
async def delete_tenant(tenant_id: str) -> dict[str, object]:
    success = await chat_service.delete_tenant(tenant_id)
    if not success:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return {"deleted": True}


# User CRUD
@router.get("/tenants/{tenant_id}/users")
async def list_tenant_users(tenant_id: str) -> dict[str, object]:
    users = await chat_service.list_tenant_users(tenant_id)
    return {"users": [asdict(u) for u in users]}


@router.post("/tenants/{tenant_id}/users")
async def create_user(tenant_id: str, payload: UserCreateRequest) -> dict[str, object]:
    try:
        user = await chat_service.create_user(
            tenant_id=tenant_id,
            user_id=payload.user_id,
            role=payload.role,
            scopes=payload.scopes,
        )
        return asdict(user)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/tenants/{tenant_id}/users/{user_id}")
async def update_user(tenant_id: str, user_id: str, payload: UserUpdateRequest) -> dict[str, object]:
    try:
        user = await chat_service.update_user(
            tenant_id=tenant_id,
            user_id=user_id,
            role=payload.role,
            scopes=payload.scopes,
        )
        return asdict(user)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/tenants/{tenant_id}/users/{user_id}")
async def delete_user(tenant_id: str, user_id: str) -> dict[str, object]:
    success = await chat_service.delete_user(tenant_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"deleted": True}


@router.get("/security")
async def security_overview(
    tenant_id: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
) -> dict[str, object]:
    try:
        return await chat_service.list_security_overview(tenant_id=tenant_id, user_id=user_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/knowledge")
async def knowledge_sources(
    tenant_id: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
) -> dict[str, object]:
    try:
        return await chat_service.list_knowledge_sources(tenant_id=tenant_id, user_id=user_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/traces")
async def list_traces(
    tenant_id: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
) -> dict[str, object]:
    try:
        return {"items": await chat_service.list_traces(tenant_id=tenant_id, user_id=user_id)}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
