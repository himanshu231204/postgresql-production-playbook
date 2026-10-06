"""Alembic environment: async (asyncpg), URL from the environment, PostgreSQL guard rails.

Run as the migration role (see 06-security/least-privilege.md), never the app role.
"""

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app.models import SCHEMA, Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    """Return the migration DB URL from the environment; fail loudly if missing."""
    url = os.environ.get("MIGRATION_DATABASE_URL")
    if not url:
        raise RuntimeError("MIGRATION_DATABASE_URL is not set")
    return url


def include_name(name: str | None, type_: str, parent_names: dict) -> bool:
    """Limit autogenerate to our schema; ignore other schemas in the database."""
    if type_ == "schema":
        return name == SCHEMA
    return True


CONTEXT_OPTS = dict(
    target_metadata=target_metadata,
    include_schemas=True,
    include_name=include_name,
    version_table_schema=SCHEMA,  # alembic_version lives in schema "app"
    compare_type=True,
    compare_server_default=True,
)


def run_migrations_offline() -> None:
    """Emit SQL to stdout (alembic upgrade head --sql); no DB connection."""
    context.configure(
        url=get_url(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **CONTEXT_OPTS,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, **CONTEXT_OPTS)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    # Session-level guard rails, sent as startup parameters so they survive
    # COMMITs inside autocommit_block(). Values are milliseconds.
    server_settings = {
        "lock_timeout": os.environ.get("MIGRATION_LOCK_TIMEOUT_MS", "5000"),
        "statement_timeout": os.environ.get("MIGRATION_STATEMENT_TIMEOUT_MS", "300000"),
        "application_name": "alembic",
    }
    connectable = create_async_engine(
        get_url(),
        poolclass=pool.NullPool,
        connect_args={"server_settings": server_settings},
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
