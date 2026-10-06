"""Async engine/session factory and the dimension guard."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def make_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, pool_pre_ping=True)


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def assert_dimension_matches(session: AsyncSession, embedder_dim: int) -> None:
    """Fail fast if the embedder and the vector(N) column disagree.

    For the vector type, pg_attribute.atttypmod stores N.
    """
    result = await session.execute(
        text(
            "SELECT atttypmod FROM pg_attribute "
            "WHERE attrelid = 'chunks'::regclass AND attname = 'embedding'"
        )
    )
    column_dim = result.scalar_one()
    if column_dim != embedder_dim:
        raise RuntimeError(
            f"Dimension mismatch: chunks.embedding is vector({column_dim}) "
            f"but the embedder produces {embedder_dim}. Re-create the column "
            "and re-embed all rows when changing models."
        )
