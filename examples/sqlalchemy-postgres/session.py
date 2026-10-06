"""Engine and session factories for the async (asyncpg) and sync (psycopg 3) stacks."""

import os

from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Environment variable {name} is not set (see .env.example)")
    return value


def make_async_engine() -> AsyncEngine:
    return create_async_engine(
        _require_env("DATABASE_URL"),
        pool_size=5,
        max_overflow=5,
        pool_timeout=10,
        pool_recycle=1800,
        pool_pre_ping=True,
        connect_args={"timeout": 10},  # asyncpg connect timeout (seconds)
    )


def make_async_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


def make_sync_engine() -> Engine:
    return create_engine(
        _require_env("SYNC_DATABASE_URL"),
        pool_size=5,
        max_overflow=5,
        pool_timeout=10,
        pool_recycle=1800,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10},  # libpq/psycopg connect timeout
    )


def make_sync_sessionmaker(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
