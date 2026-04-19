from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from agent_platform.bootstrap.settings import settings


class Base(DeclarativeBase):
    pass


def normalize_database_url(url: str) -> str:
    parsed = make_url(url)
    if parsed.drivername == "postgresql":
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    if not parsed.drivername.startswith("postgresql+psycopg"):
        raise ValueError("AOP_DATABASE_URL must point to PostgreSQL using postgresql:// or postgresql+psycopg://")
    return url


class DatabaseRuntime:
    def __init__(self, database_url: str | None) -> None:
        if not database_url:
            raise RuntimeError("AOP_DATABASE_URL is required. The platform runs only with PostgreSQL.")
        self._database_url = normalize_database_url(database_url)
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    @property
    def enabled(self) -> bool:
        return True

    @property
    def engine(self) -> AsyncEngine | None:
        return self._engine

    def create_engine(self) -> AsyncEngine | None:
        if self._engine is None:
            self._engine = create_async_engine(
                self._database_url,
                future=True,
                pool_pre_ping=True,
            )
            self._session_factory = async_sessionmaker(
                bind=self._engine,
                expire_on_commit=False,
            )
        return self._engine

    async def initialize(self) -> None:
        self.run_migrations()
        self.create_engine()

    def run_migrations(self) -> None:
        project_root = Path(__file__).resolve().parents[5]
        config = Config(str(project_root / "alembic.ini"))
        config.set_main_option("script_location", str(project_root / "migrations"))
        command.upgrade(config, "head")

    async def healthcheck(self) -> dict[str, object]:
        engine = self.create_engine()
        try:
            async with engine.connect() as conn:
                await conn.execute(text("select 1"))
            return {"enabled": True, "connected": True, "detail": "ok"}
        except Exception as exc:  # noqa: BLE001
            return {"enabled": True, "connected": False, "detail": str(exc)}

    @asynccontextmanager
    async def session(self) -> AsyncSession:
        if self._session_factory is None:
            self.create_engine()
        if self._session_factory is None:
            raise RuntimeError("Database runtime is not configured")
        async with self._session_factory() as session:
            yield session


db_runtime = DatabaseRuntime(settings.database_url)
