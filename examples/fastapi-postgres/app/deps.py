"""FastAPI dependencies: one AsyncSession per request."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    sessionmaker: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    # Leaving the block closes the session: the connection returns to the pool
    # and any uncommitted transaction is rolled back.
    async with sessionmaker() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]
