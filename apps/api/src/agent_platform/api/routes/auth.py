from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from agent_platform.api.errors import (
    ERROR_CODE_AUTH_USER_NOT_FOUND,
    ERROR_CODE_INVALID_OR_EXPIRED_TOKEN,
    ERROR_CODE_MISSING_AUTH_CONTEXT,
    ERROR_CODE_MISSING_TOKEN,
    raise_http_error,
)
from agent_platform.bootstrap.container import chat_service
from agent_platform.domain.models import UserContext
from agent_platform.infrastructure.auth import create_access_token, decode_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str = Field(..., description="用户邮箱")
    password: str = Field(..., min_length=6, description="密码")


class RegisterRequest(BaseModel):
    email: str = Field(..., description="用户邮箱")
    password: str = Field(..., min_length=6, description="密码")
    tenant_id: str = Field(..., description="租户 ID")
    role: str = Field(default="platform_admin", description="角色")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


async def _build_auth_user_payload(user_context: UserContext) -> dict[str, str]:
    tenant = await chat_service.get_tenant(user_context.tenant_id)
    return {
        "user_id": user_context.user_id,
        "tenant_id": user_context.tenant_id,
        "role": user_context.role,
        "email": user_context.email,
        "tenant_name": tenant.name if tenant else user_context.tenant_id,
    }


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest) -> dict[str, object]:
    result = await chat_service.authenticate_user(email=payload.email, password=payload.password)
    if result is None:
        raise HTTPException(status_code=401, detail="邮箱或密码错误")

    user_context, _ = result
    access_token = create_access_token(
        data={
            "sub": user_context.user_id,
            "tenant_id": user_context.tenant_id,
            "email": payload.email,
        }
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": await _build_auth_user_payload(user_context),
    }


@router.post("/register", response_model=TokenResponse)
async def register(payload: RegisterRequest) -> dict[str, object]:
    result = await chat_service.register_user(
        email=payload.email,
        password=payload.password,
        tenant_id=payload.tenant_id,
        role=payload.role,
    )
    if result is None:
        raise HTTPException(status_code=400, detail="邮箱已被注册或租户不存在")

    user_context, _ = result
    access_token = create_access_token(
        data={
            "sub": user_context.user_id,
            "tenant_id": user_context.tenant_id,
            "email": payload.email,
        }
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": await _build_auth_user_payload(user_context),
    }


@router.get("/me")
async def get_current_user(authorization: str | None = Header(default=None)) -> dict[str, str]:
    if not authorization or not authorization.startswith("Bearer "):
        raise_http_error(status_code=401, code=ERROR_CODE_MISSING_TOKEN, detail="缺少认证令牌")

    payload = decode_access_token(authorization.removeprefix("Bearer ").strip())
    if payload is None:
        raise_http_error(status_code=401, code=ERROR_CODE_INVALID_OR_EXPIRED_TOKEN, detail="认证令牌无效或已过期")

    user_id = payload.get("sub")
    tenant_id = payload.get("tenant_id")
    if not user_id or not tenant_id:
        raise_http_error(status_code=401, code=ERROR_CODE_MISSING_AUTH_CONTEXT, detail="认证令牌缺少用户上下文")

    user_context = await chat_service.get_user(tenant_id=tenant_id, user_id=user_id)
    if user_context is None:
        raise_http_error(status_code=404, code=ERROR_CODE_AUTH_USER_NOT_FOUND, detail="用户不存在")

    return await _build_auth_user_payload(user_context)
