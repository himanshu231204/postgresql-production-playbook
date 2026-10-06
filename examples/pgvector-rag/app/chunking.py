"""Fixed-size character chunking with overlap.

Chunking strategy affects retrieval quality as much as the index does.
Character windows are the simplest option; production systems often split on
headings/paragraphs/sentences and size chunks in tokens of the target model.
"""


def chunk_text(text: str, size: int, overlap: int) -> list[str]:
    if size <= 0:
        raise ValueError("size must be positive")
    if not 0 <= overlap < size:
        raise ValueError("overlap must be >= 0 and < size")
    cleaned = " ".join(text.split())
    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        piece = cleaned[start : start + size].strip()
        if piece:
            chunks.append(piece)
        if start + size >= len(cleaned):
            break
        start += size - overlap
    return chunks
