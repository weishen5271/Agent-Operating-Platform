from __future__ import annotations

from fastapi import APIRouter, Query

from agent_platform.bootstrap.container import chat_service

router = APIRouter(prefix="/workspace", tags=["workspace"])


@router.get("/home")
async def get_home(
    tenant_id: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
) -> dict[str, object]:
    return await chat_service.home_snapshot(tenant_id=tenant_id, user_id=user_id)
