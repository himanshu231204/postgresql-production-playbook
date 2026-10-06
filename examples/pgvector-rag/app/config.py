"""Configuration from environment variables only."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    database_url: str
    embedding_dim: int
    chunk_size: int
    chunk_overlap: int
    top_k: int


def load_settings() -> Settings:
    load_dotenv()
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set (see .env.example)")
    return Settings(
        database_url=database_url,
        embedding_dim=int(os.environ.get("EMBEDDING_DIM", "384")),
        chunk_size=int(os.environ.get("CHUNK_SIZE", "600")),
        chunk_overlap=int(os.environ.get("CHUNK_OVERLAP", "100")),
        top_k=int(os.environ.get("TOP_K", "4")),
    )
