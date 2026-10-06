# Embeddings in PostgreSQL

## What it is

An embedding is a fixed-length array of numbers that a model produces for a
piece of content (text chunk, image, ...). pgvector stores it in a typed
column so SQL can compare embeddings by distance. Embeddings come from an
embedding model outside the database; PostgreSQL does not generate them.

## Why it matters

Three coupled decisions are hard to change later: the **column dimension**,
the **model that produced the vectors**, and the **distance metric**. Vectors
from different models (or different versions of one model) are not comparable
even when their dimensions happen to match.

## Syntax

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE chunks (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    content     TEXT   NOT NULL,
    embedding   vector(384) NOT NULL,   -- 384 must equal your model's output size
    embedder    TEXT   NOT NULL         -- model name + version that produced it
);
```

Insert with a text literal or, from Python, a list/NumPy array via the
`pgvector` package (see [Python](#python-sqlalchemy-2x-and-asyncpg)):

```sql
INSERT INTO chunks (document_id, content, embedding, embedder)
VALUES (1, 'example', '[0.1, 0.2, 0.3, ...]', 'my-model-v1');
```

`'[...]'` must contain exactly as many elements as the column dimension, or
PostgreSQL raises `expected 384 dimensions, not N`.

## Types and limits

| Type | Element | Storage | Max dims (stored) | Max dims (indexed with HNSW/IVFFlat) |
|---|---|---|---|---|
| `vector` | 32-bit float | `4 * dims + 8` bytes | 16,000 | 2,000 |
| `halfvec` (0.7.0+) | 16-bit float | `2 * dims + 8` bytes | 16,000 | 4,000 |
| `bit` (0.7.0+ for indexing) | bit | | | 64,000 |
| `sparsevec` (0.7.0+) | non-zero elements only | | | 1,000 non-zero elements (HNSW) |

Source: pgvector README. Storage formula confirmed on 0.8.1:
`pg_column_size('[1,2,3]'::vector)` returned `20` (= 4*3 + 8).

Consequence: a model that outputs more than 2,000 dimensions cannot use a
`vector` index directly. Options: store as `halfvec` (index up to 4,000),
use a model that supports reduced output dimensions, or index a
`halfvec` cast expression:

```sql
CREATE INDEX ON chunks USING hnsw ((embedding::halfvec(3072)) halfvec_cosine_ops);
-- queries must use the same expression: ORDER BY embedding::halfvec(3072) <=> $1::halfvec(3072)
```

This expression-index form follows the pgvector README ("Half-Precision
Indexing"). On 0.8.1 the `CREATE INDEX` succeeded on a 3,000-dimension
`vector` column; planner use of it was not demonstrated (the test table was
too small to prefer an index scan), so confirm with `EXPLAIN` on your data.
Lower precision and fewer dimensions reduce memory and index size at some
cost in recall; measure it on your data.

## Dimension must match the model

- `vector(N)` is enforced on insert: wrong-length vectors are rejected.
- Same dimension is not enough. Switching from model A to model B with the
  same dimension silently mixes incompatible vector spaces and returns
  meaningless neighbors.
- Record the producer per row (`embedder` column above) so a migration to a
  new model is detectable and resumable.

Model change procedure: add a new column (`embedding_v2 vector(M)`), backfill
in batches, build the new index `CONCURRENTLY`, switch queries, then drop the old
column in a later release. Dropping the old column is destructive; confirm a
backup first. See [09-alembic/production-migrations.md](../09-alembic/production-migrations.md).

## Normalization

Many embedding models return unit-length vectors; some do not. For
unit-length vectors, cosine distance and inner product rank identically, and
inner product (`<#>`) is cheaper to compute. Check your model's documentation
rather than assuming. To normalize in SQL:

```sql
SELECT l2_normalize('[3,4]'::vector);   -- [0.6,0.8]   (0.7.0+)
```

Do not normalize if you intend to use L2 distance for magnitude-sensitive
comparisons; pick the metric your model was trained for (see
[similarity-search.md](similarity-search.md)).

## Chunking and quality

Retrieval quality depends on chunking and embedding strategy, not only the
index. An HNSW index returns the nearest vectors to the query; if chunks split
sentences mid-thought, are too large to be specific, or the model is a poor fit
for your domain, the "nearest" chunk is still wrong. Decisions to make
explicitly:

- Chunk size and overlap (characters or model tokens), and whether to split on headings/paragraphs.
- Whether to embed the title/section path along with the chunk text.
- Query vs. document embedding (some models use different prefixes or modes for each).
- Maximum input length of the model (longer text is truncated or rejected).

## Python (SQLAlchemy 2.x and asyncpg)

```python
from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import Mapped, mapped_column

EMBEDDING_DIM = 384  # must match the model and the vector(N) column

class Chunk(Base):
    __tablename__ = "chunks"
    id: Mapped[int] = mapped_column(primary_key=True)
    content: Mapped[str]
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
```

A complete, runnable version (with a stub embedder and a dimension guard) is in
[examples/pgvector-rag/](../examples/pgvector-rag/README.md).

## Production usage

- Compute embeddings **outside** the write transaction (network call to the
  model); then insert text and vector together in one short transaction.
- Make ingestion idempotent: unique key on `(document_id, chunk_index)` or a
  content hash, so a retried job does not duplicate chunks.
- Load large datasets with `COPY` and build the index afterward.
- Treat embedded text as untrusted input if it comes from users or the web.

## Common mistakes

- Column `vector(1536)` but the deployed model outputs a different size.
- Changing the embedding model without re-embedding stored rows.
- Embedding queries with a different model/preprocessing than documents.
- Storing only the vector and losing the source text/version needed to re-embed.

## Performance considerations

Each `vector(N)` row costs `4N + 8` bytes before TOAST/index overhead; the
index and the heap both compete for memory. `halfvec` halves the vector
storage. Estimate with `pg_total_relation_size('chunks')` after loading a
sample, not from formulas alone.

## Quick revision

- Dimension is part of the schema and must equal the model output.
- Same dimension from a different model is still incompatible.
- `vector` indexes cap at 2,000 dims; `halfvec` at 4,000.
- Record which model produced each row.
