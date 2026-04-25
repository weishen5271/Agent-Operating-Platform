from __future__ import annotations

from fastapi import APIRouter

from agent_platform.api.deps import AuthContext
from agent_platform.bootstrap.container import chat_service

router = APIRouter(prefix="/workspace", tags=["workspace"])


@router.get("/home")
async def get_home(auth: AuthContext) -> dict[str, object]:
    tenant_id, user_id = auth
    return await chat_service.home_snapshot(tenant_id=tenant_id, user_id=user_id)
