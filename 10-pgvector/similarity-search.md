# Similarity Search

## What it is

Finding the rows whose embeddings are closest to a query embedding, using a
distance operator in `ORDER BY ... LIMIT k`. Without an index this is **exact**
(compares every row). With an HNSW or IVFFlat index it is **approximate**.

## Why it matters

The operator you query with must match the operator class the index was built
with, or the planner cannot use the index. And approximate indexes change
results: filtering, `LIMIT`, and tuning settings all affect recall.

## Syntax

```sql
-- $1 is the query embedding, same model and dimension as the column
SELECT id, content, embedding <=> $1 AS cosine_distance
FROM chunks
ORDER BY embedding <=> $1
LIMIT 5;
```

| Operator | Metric | Index operator class | Notes |
|---|---|---|---|
| `<->` | L2 (Euclidean) distance | `vector_l2_ops` | |
| `<#>` | **Negative** inner product | `vector_ip_ops` | Negated because PostgreSQL index scans return ascending order; multiply by -1 for the inner product |
| `<=>` | Cosine distance | `vector_cosine_ops` | `1 - cosine similarity` |
| `<+>` | L1 (taxicab) distance | `vector_l1_ops` | 0.7.0+ |

For `halfvec` use `halfvec_*_ops`; bit vectors use Hamming/Jaccard operators
(see the pgvector README). Verified on 0.8.1:
`SELECT '[1,2,3]'::vector <#> '[1,2,3]'` returns `-14`.

## Choosing a metric

Use the metric the embedding model was trained/evaluated with; the model's
documentation says which. Common situation: text embedding models are
typically used with cosine similarity. If vectors are unit length, cosine and
inner product give the same ranking and `<#>` avoids the norm computation;
L2 also gives the same ranking on unit vectors. If you are unsure whether
your vectors are normalized, use cosine, which is insensitive to length.

Pick one metric per column and build one index for it. An index built with
`vector_cosine_ops` is not used for `<->` queries (verified: on the test table
the `<->` query used a sequential scan until an L2 index existed).

## Exact vs. approximate

| | Exact (no index) | Approximate (HNSW / IVFFlat) |
|---|---|---|
| Recall | Perfect | Below 100%, tunable |
| Latency | Grows with row count (full scan) | Sublinear; depends on parameters |
| Results change after adding an index | n/a | Yes |
| Good for | Small tables, highly selective filters, ground truth for recall tests | Large tables with `ORDER BY ... LIMIT` |

Exact search is not a failure mode. For a few thousand rows, or when a `WHERE`
clause narrows candidates to a small set, a sequential scan with a sort can
be fast enough and has perfect recall. Increase `max_parallel_workers_per_gather`
to speed up exact scans (pgvector README).

## Verify the index is used

```sql
EXPLAIN SELECT id FROM chunks ORDER BY embedding <=> $1 LIMIT 5;
```

Expected with an HNSW cosine index (validated, PostgreSQL 16 + pgvector 0.8.1):

```text
Limit
  ->  Index Scan using chunks_embedding_hnsw on chunks
        Order By: (embedding <=> '[...]'::vector)
```

`Seq Scan` + `Sort` means no usable index: operator mismatch (`<->` vs.
cosine index), missing `LIMIT`, an `ORDER BY` that is not directly
`column <op> value`, or the planner judged a scan cheaper (small table). See
[05-performance/explain.md](../05-performance/explain.md). Use
`EXPLAIN (ANALYZE, BUFFERS)` for timing. On tiny tables the planner may
legitimately prefer a sequential scan; test on realistic row counts.

Index scans require `ORDER BY <distance> ASC LIMIT n`. Ordering `DESC`, or
ordering by `1 - (embedding <=> $1)`, does not use the index; select the
similarity as a separate column and order by the raw distance expression.

## Measuring recall

Ground truth comes from exact search. Run on a sample of real queries:

```sql
-- approximate result (uses the index)
CREATE TEMP TABLE approx AS
SELECT id FROM chunks ORDER BY embedding <=> $1 LIMIT 10;

-- exact result: disable index paths inside a transaction
BEGIN;
SET LOCAL enable_indexscan = off;
SET LOCAL enable_bitmapscan = off;
CREATE TEMP TABLE exact AS
SELECT id FROM chunks ORDER BY embedding <=> $1 LIMIT 10;
COMMIT;

SELECT count(*)::float / 10 AS recall_at_10
FROM approx JOIN exact USING (id);
```

(`$1` is a placeholder for the query vector; in `psql` use a literal.) The
session-scoped settings above only affect your session and are used only to
produce ground truth. Average across many queries, not one. Tuning guidance
is in [indexing.md](indexing.md).

## Metadata filtering

```sql
SELECT id, content
FROM chunks
WHERE category = $2
ORDER BY embedding <=> $1
LIMIT 5;
```

Behavior with approximate indexes: the index returns its nearest candidates
**first**, then `WHERE` is applied. If the filter matches a small fraction of
rows, fewer than `LIMIT` rows can come back (pgvector README: with a condition
matching 10% of rows and default `hnsw.ef_search = 40`, about 4 rows survive on
average). Options, with tradeoffs:

| Approach | Use when | Tradeoff |
|---|---|---|
| B-tree on the filter column (`CREATE INDEX ON chunks (category)`) | Filter is selective; planner can filter first and sort exactly | Exact results, but cost grows with matching rows; extra write cost |
| Iterative index scans (0.8.0+) | Filter is moderately selective and recall matters | Scans more of the index when needed; slower for rare filters; bounded by `hnsw.max_scan_tuples` (default 20,000) / `ivfflat.max_probes` |
| Partial index (`... WHERE category = 'x'`) | A few known filter values | One index per value; queries must repeat the predicate |
| Partitioning by filter column | Many values, tenant isolation | Planner must prune partitions; more objects to manage |
| Raise `hnsw.ef_search` | Mild filtering | Slower every query |

Enable iterative scans per transaction:

```sql
BEGIN;
SET LOCAL hnsw.iterative_scan = strict_order;   -- or relaxed_order
SELECT id FROM chunks WHERE category = 'security' ORDER BY embedding <=> $1 LIMIT 10;
COMMIT;
```

`strict_order` keeps exact distance ordering; `relaxed_order` may return
results slightly out of order for better recall. Details in
[indexing.md](indexing.md#iterative-index-scans-pgvector-080). Always pass
filter values as bind parameters; never format them into the SQL string.

Hybrid retrieval (full-text search plus vectors) is possible in PostgreSQL;
combine results with a ranking method such as reciprocal rank fusion. Not
covered or validated here.

## Python

```python
from sqlalchemy import select

distance = Chunk.embedding.cosine_distance(query_vector).label("distance")
stmt = select(Chunk.content, distance).order_by(distance).limit(5)
rows = (await session.execute(stmt)).all()
```

See the runnable [examples/pgvector-rag/](../examples/pgvector-rag/README.md).
SQLAlchemy 2.x; the `pgvector.sqlalchemy` comparators are `l2_distance`,
`max_inner_product`, `cosine_distance`, `l1_distance`.

## Common mistakes

- Querying with `<->` against a cosine index (or vice versa): silent seq scan.
- Different model or preprocessing for query and documents.
- Expecting `LIMIT 10` plus a restrictive `WHERE` to always return 10 rows with an approximate index.
- Comparing similarity scores across models or against a fixed cutoff. Score distributions are model-specific; derive any threshold from your own evaluation, not from a universal number.
- Judging quality by "an index is used" rather than measuring recall and answer quality.

## Quick revision

- Operator must match the index operator class; `ORDER BY dist ASC LIMIT k`.
- `<#>` is negative inner product.
- Verify with `EXPLAIN`; measure recall against exact search.
- Approximate index + `WHERE` = post-filter; use iterative scans, partial indexes, or partitions.
