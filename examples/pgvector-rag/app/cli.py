"""CLI: `python -m app.cli ingest` / `python -m app.cli ask "question" [--category X] [--explain]`."""

import argparse
import asyncio
from pathlib import Path

from sqlalchemy import text

from app.config import load_settings
from app.db import assert_dimension_matches, make_engine, make_session_factory
from app.embeddings import get_embedder
from app.ingest import ingest_document, read_sample_docs
from app.retrieval import build_prompt, search

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_docs"


async def run(args: argparse.Namespace) -> None:
    settings = load_settings()
    embedder = get_embedder(settings.embedding_dim)
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)
    try:
        async with session_factory() as session:
            await assert_dimension_matches(session, embedder.dimension)
            if args.command == "ingest":
                for source, title, category, body in read_sample_docs(SAMPLE_DIR):
                    count = await ingest_document(
                        session,
                        embedder,
                        source=source,
                        title=title,
                        category=category,
                        text=body,
                        chunk_size=settings.chunk_size,
                        chunk_overlap=settings.chunk_overlap,
                    )
                    print(f"ingested {source}: {count} chunks")
            else:
                hits = await search(
                    session, embedder, args.question, top_k=settings.top_k, category=args.category
                )
                for hit in hits:
                    print(
                        f"{hit.cosine_distance:.4f}  {hit.source}#{hit.chunk_index}  {hit.content[:80]}..."
                    )
                print("\n--- prompt for your LLM ---")
                print(build_prompt(args.question, hits))
                if args.explain:
                    await explain(session, embedder.embed([args.question])[0])
    finally:
        await engine.dispose()


async def explain(session, query_vector: list[float]) -> None:
    """Print the plan (long vector literals truncated). Confirm an Index Scan on the HNSW index."""
    literal = "[" + ",".join(f"{v:.6f}" for v in query_vector) + "]"
    result = await session.execute(
        text("EXPLAIN SELECT id FROM chunks ORDER BY embedding <=> CAST(:q AS vector) LIMIT 4"),
        {"q": literal},
    )
    print("\n--- EXPLAIN ---")
    for (line,) in result.all():
        print(line if len(line) <= 120 else line[:117] + "...")


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("ingest")
    ask = sub.add_parser("ask")
    ask.add_argument("question")
    ask.add_argument("--category")
    ask.add_argument("--explain", action="store_true")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
