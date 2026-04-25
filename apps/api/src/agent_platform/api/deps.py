from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Query

from agent_platform.infrastructure.auth import decode_access_token


def resolve_auth_context(
    authorization: str | None = Header(default=None),
    tenant_id: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
) -> tuple[str | None, str | None]:
    """解析当前请求所属的 (tenant_id, user_id)。

    优先使用 JWT 中的身份信息——这是服务端唯一可信的租户来源，避免前端误传或缺失
    导致写入错误的租户。仅在没有 Authorization header（如脚本/调试）时退回到查询
    参数，保持兼容性。
    """

    if authorization:
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

    return tenant_id, user_id


AuthContext = Annotated[tuple[str | None, str | None], Depends(resolve_auth_context)]
