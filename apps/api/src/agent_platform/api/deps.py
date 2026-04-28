from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header

from agent_platform.api.errors import (
    ERROR_CODE_INVALID_OR_EXPIRED_TOKEN,
    ERROR_CODE_INVALID_TOKEN_FORMAT,
    ERROR_CODE_MISSING_AUTH_CONTEXT,
    ERROR_CODE_MISSING_TOKEN,
    raise_http_error,
)
from agent_platform.infrastructure.auth import decode_access_token


def resolve_auth_context(
    authorization: str | None = Header(default=None),
) -> tuple[str, str]:
    """解析当前请求所属的 (tenant_id, user_id)。

    JWT 中的身份信息是服务端唯一可信的租户来源，避免前端误传、缺失或空白
    Authorization 时落到默认租户，造成跨租户数据泄露。
    """

    if not authorization or not authorization.strip():
        raise_http_error(status_code=401, code=ERROR_CODE_MISSING_TOKEN, detail="缺少认证令牌")
    if not authorization.startswith("Bearer "):
        raise_http_error(status_code=401, code=ERROR_CODE_INVALID_TOKEN_FORMAT, detail="认证令牌格式无效")

    payload = decode_access_token(authorization.removeprefix("Bearer ").strip())
    if payload is None:
        raise_http_error(status_code=401, code=ERROR_CODE_INVALID_OR_EXPIRED_TOKEN, detail="认证令牌无效或已过期")
    token_user_id = payload.get("sub")
    token_tenant_id = payload.get("tenant_id")
    if not token_user_id or not token_tenant_id:
        raise_http_error(status_code=401, code=ERROR_CODE_MISSING_AUTH_CONTEXT, detail="认证令牌缺少用户上下文")
    return token_tenant_id, token_user_id


AuthContext = Annotated[tuple[str, str], Depends(resolve_auth_context)]
