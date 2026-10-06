"""Idempotent ingestion: re-ingesting a source replaces its chunks in one transaction."""

from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.chunking import chunk_text
from app.embeddings import Embedder
from app.models import Chunk, Document


async def ingest_document(
    session: AsyncSession,
    embedder: Embedder,
    *,
    source: str,
    title: str,
    category: str,
    text: str,
    chunk_size: int,
    chunk_overlap: int,
) -> int:
    pieces = chunk_text(text, chunk_size, chunk_overlap)
    vectors = embedder.embed(pieces)  # one batched call; embed outside DB locks in real use

    existing = await session.scalar(select(Document).where(Document.source == source))
    if existing is None:
        document = Document(source=source, title=title, category=category)
        session.add(document)
        await session.flush()
    else:
        document = existing
        document.title = title
        document.category = category
        await session.execute(delete(Chunk).where(Chunk.document_id == document.id))

    session.add_all(
        Chunk(
            document_id=document.id,
            chunk_index=index,
            content=piece,
            category=category,
            embedding=vector,
            embedder=embedder.name,
        )
        for index, (piece, vector) in enumerate(zip(pieces, vectors, strict=True))
    )
    await session.commit()
    return len(pieces)


def read_sample_docs(directory: Path) -> list[tuple[str, str, str, str]]:
    """Return (source, title, category, text). First line: `category: x`; second: `# Title`."""
    docs: list[tuple[str, str, str, str]] = []
    for path in sorted(directory.glob("*.md")):
        lines = path.read_text(encoding="utf-8").splitlines()
        category = lines[0].split(":", 1)[1].strip()
        title = lines[1].lstrip("# ").strip()
        docs.append((path.name, title, category, "\n".join(lines[2:])))
    return docs
