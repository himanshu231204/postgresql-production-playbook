"""Embedding interface plus a deterministic STUB implementation.

The stub is NOT a semantic model. It hashes tokens into a fixed-size
bag-of-words vector, so it only captures shared-word overlap. It exists so
this example runs offline with no API key. Retrieval quality with the stub
says nothing about retrieval quality with a real model.

To use a real model, implement `Embedder` (see the commented sketch at the
bottom) and return it from `get_embedder()`. Its `dimension` MUST equal the
`vector(N)` size in schema.sql and EMBEDDING_DIM; if it does not, inserts fail
or, worse, you compare vectors from different models. Changing models means
re-embedding every stored row.
"""

import hashlib
import math
import re
from typing import Protocol

_TOKEN = re.compile(r"[a-z0-9]+")


class Embedder(Protocol):
    name: str
    dimension: int

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one L2-normalized vector of length `dimension` per text."""
        ...


class StubEmbedder:
    """Deterministic hashed bag-of-words embedder. For demos and tests only."""

    def __init__(self, dimension: int) -> None:
        self.dimension = dimension
        self.name = f"stub-hashed-bow-{dimension}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in _TOKEN.findall(text.lower()):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return vector  # empty text; callers should skip empty chunks
        return [value / norm for value in vector]


def get_embedder(dimension: int) -> Embedder:
    """Single place to swap in a real embedding model."""
    return StubEmbedder(dimension)


# --- Sketch of a real implementation (not executed; adapt to your provider) ---
#
# class ProviderEmbedder:
#     name = "your-model-name"
#     dimension = 384  # whatever your model outputs; fixed per model
#
#     def embed(self, texts: list[str]) -> list[list[float]]:
#         response = client.embeddings.create(model=self.name, input=texts)
#         return [item.embedding for item in response.data]
#
# Read the API key from an environment variable, never from source code.
