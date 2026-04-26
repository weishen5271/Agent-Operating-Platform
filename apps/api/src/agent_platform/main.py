from __future__ import annotations

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from agent_platform.api.routes.admin import router as admin_router
from agent_platform.api.routes.auth import router as auth_router
from agent_platform.api.routes.chat import router as chat_router
from agent_platform.api.routes.outputs import router as outputs_router
from agent_platform.api.routes.workspace import router as workspace_router
from agent_platform.bootstrap.container import initialize_runtime_state
from agent_platform.bootstrap.settings import settings
from agent_platform.infrastructure.db import db_runtime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("agent_platform.api")


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
app.include_router(outputs_router, prefix=settings.api_prefix)
app.include_router(admin_router, prefix=settings.api_prefix)
app.include_router(auth_router, prefix=settings.api_prefix)


@app.exception_handler(ValueError)
async def handle_value_error(request: Request, exc: ValueError) -> JSONResponse:
    logger.warning("ValueError on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, HTTPException):
        raise exc
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": f"{exc.__class__.__name__}: {exc}"},
    )


@app.get("/healthz")
async def healthcheck() -> dict[str, object]:
    return {
        "status": "ok",
        "database": await db_runtime.healthcheck(),
    }
