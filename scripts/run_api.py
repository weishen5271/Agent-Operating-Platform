from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import traceback
from pathlib import Path
from typing import Any

import uvicorn


PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_SRC = PROJECT_ROOT / "apps" / "api" / "src"


def ensure_import_path() -> None:
    api_src = str(API_SRC)
    if api_src not in sys.path:
        sys.path.insert(0, api_src)


def validate_database_config() -> None:
    if os.getenv("AOP_DATABASE_URL") or (PROJECT_ROOT / "config.toml").exists():
        return
    raise RuntimeError(
        "数据库未配置。请创建 config.toml 文件或设置 AOP_DATABASE_URL 环境变量。"
        "参考示例: Copy-Item config.toml.example config.toml"
    )


def configure_event_loop_policy() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start Agent Operating Platform API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--log-level", default="info", choices=["critical", "error", "warning", "info", "debug", "trace"])
    parser.add_argument("--no-access-log", action="store_true", help="Disable HTTP access logs.")
    parser.add_argument("--reload", action="store_true", help="Enable uvicorn reload outside debugger.")
    return parser.parse_args()


def configure_logging(log_level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        force=True,
    )


def load_debug_app() -> Any:
    from agent_platform import main as app_module

    print(f"Loaded app module: {Path(app_module.__file__).resolve()}", flush=True)
    print(f"Process ID: {os.getpid()}", flush=True)
    return app_module.app


def main() -> None:
    args = parse_args()
    os.chdir(PROJECT_ROOT)
    configure_event_loop_policy()
    ensure_import_path()
    validate_database_config()
    configure_logging(args.log_level)
    print(f"Starting Agent Operating Platform API at http://{args.host}:{args.port}", flush=True)
    print(f"OpenAPI docs: http://{args.host}:{args.port}/docs", flush=True)
    print(f"Working directory: {PROJECT_ROOT}", flush=True)
    if args.reload:
        uvicorn.run(
            "agent_platform.main:app",
            host=args.host,
            port=args.port,
            loop="asyncio",
            log_level=args.log_level,
            access_log=not args.no_access_log,
            reload=True,
        )
        return

    app = load_debug_app()
    config = uvicorn.Config(
        app,
        host=args.host,
        port=args.port,
        loop="asyncio",
        log_level=args.log_level,
        access_log=not args.no_access_log,
    )
    server = uvicorn.Server(config)
    if sys.platform == "win32":
        loop = asyncio.SelectorEventLoop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(server.serve())
        finally:
            loop.close()
        return
    asyncio.run(server.serve())


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise
