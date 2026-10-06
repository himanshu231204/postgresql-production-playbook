"""Application entry point: uvicorn app.main:app"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.db import build_engine, build_sessionmaker
from app.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    engine = build_engine(settings)
    app.state.engine = engine
    app.state.sessionmaker = build_sessionmaker(engine)
    try:
        yield
    finally:
        # Close pooled connections cleanly on shutdown.
        await engine.dispose()


app = FastAPI(title="fastapi-postgres", lifespan=lifespan)
app.include_router(router)
