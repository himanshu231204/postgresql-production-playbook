"""Engine and session factory construction (SQLAlchemy 2.x, asyncpg)."""

import ssl
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.config import Settings


def build_connect_args(settings: Settings) -> dict[str, Any]:
    connect_args: dict[str, Any] = {
        # asyncpg: seconds to establish the connection.
        "timeout": settings.db_connect_timeout,
        # Startup parameters. PgBouncer rejects unknown startup parameters
        # unless listed in ignore_startup_parameters; prefer
        # ALTER ROLE app_api SET statement_timeout there.
        "server_settings": {
            "application_name": settings.app_name,
            "statement_timeout": str(settings.db_statement_timeout_ms),
        },
    }
    if settings.db_ssl_ca_file:
        # create_default_context() enables CERT_REQUIRED and check_hostname,
        # i.e. verify-full semantics.
        connect_args["ssl"] = ssl.create_default_context(cafile=settings.db_ssl_ca_file)
    if settings.db_disable_statement_cache:
        # Both caches: SQLAlchemy's (prepared_statement_cache_size) and
        # asyncpg's own (statement_cache_size). Unique names avoid
        # "prepared statement already exists" behind PgBouncer.
        connect_args["prepared_statement_cache_size"] = 0
        connect_args["statement_cache_size"] = 0
        connect_args["prepared_statement_name_func"] = lambda: f"__asyncpg_{uuid4()}__"
    return connect_args


def build_engine(settings: Settings) -> AsyncEngine:
    kwargs: dict[str, Any] = {
        "echo": settings.db_echo,
        "connect_args": build_connect_args(settings),
    }
    if settings.db_use_null_pool:
        kwargs["poolclass"] = NullPool
    else:
        kwargs.update(
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout,
            pool_recycle=settings.db_pool_recycle,
            pool_pre_ping=settings.db_pool_pre_ping,
        )
    return create_async_engine(settings.database_url.get_secret_value(), **kwargs)


def build_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    # expire_on_commit=False: attributes stay readable after commit() without
    # an implicit lazy load, which is not possible in asyncio.
    return async_sessionmaker(engine, expire_on_commit=False)
