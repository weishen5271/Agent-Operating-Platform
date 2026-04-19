from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent_platform.api.routes.admin import router as admin_router
from agent_platform.api.routes.auth import router as auth_router
from agent_platform.api.routes.chat import router as chat_router
from agent_platform.api.routes.workspace import router as workspace_router
from agent_platform.bootstrap.container import initialize_runtime_state
from agent_platform.bootstrap.settings import settings
from agent_platform.infrastructure.db import db_runtime


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await db_runtime.initialize()
    await initialize_runtime_state()
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router, prefix=settings.api_prefix)
app.include_router(workspace_router, prefix=settings.api_prefix)
app.include_router(admin_router, prefix=settings.api_prefix)
app.include_router(auth_router, prefix=settings.api_prefix)


@app.get("/healthz")
async def healthcheck() -> dict[str, object]:
    return {
        "status": "ok",
        "database": await db_runtime.healthcheck(),
    }
