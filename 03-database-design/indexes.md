# Indexes (Design)

This page covers **choosing and designing** an index — type, columns,
and structure. For monitoring existing indexes (usage stats, bloat,
finding unused ones), see [05-performance/indexes.md](../05-performance/indexes.md).
For reading `EXPLAIN` output to confirm an index is actually used, see
[05-performance/explain.md](../05-performance/explain.md).

## What it is

A separate structure PostgreSQL maintains alongside a table so it can
find matching rows without scanning every row.

## Why it matters

Per [AGENTS.md](../AGENTS.md#8-database-design-rules): every index has a
cost (extra storage, slower writes, since every `INSERT`/`UPDATE`
maintains every index on the row) as well as a benefit (faster reads for
the query pattern it serves). An index with no matching query pattern is
pure cost.

## Index types

| Type | Best for | Notes |
|---|---|---|
| B-tree (default) | Equality and range queries (`=`, `<`, `>`, `BETWEEN`, sorting) | What `CREATE INDEX` gives you without specifying a type |
| GIN | Full-text search, `JSONB` containment (`@>`), array containment | Larger, slower to update than B-tree; fast for "does this contain X" queries |
| GiST | Geometric types, range types, exclusion constraints | Also used by `EXCLUDE` constraints (see [constraints.md](constraints.md)) |
| BRIN | Very large tables where the column is naturally correlated with physical row order (e.g. an append-only `created_at`) | Much smaller than a B-tree on the same column, but only useful when that physical correlation actually holds |
| Hash | Equality only | Rarely needed — a B-tree already handles equality well and supports range queries too |

For vector similarity search (HNSW/IVFFlat), see
[10-pgvector/indexing.md](../10-pgvector/indexing.md) — a specialized
case beyond these general-purpose types.

## Composite indexes: column order matters

A multi-column index only helps a query that filters on a *prefix* of
its columns, left to right:

```sql
CREATE INDEX ON orders (customer_id, status);

-- Uses the index (matches the leftmost column, or both):
SELECT * FROM orders WHERE customer_id = 1;
SELECT * FROM orders WHERE customer_id = 1 AND status = 'pending';

-- Does NOT use this index efficiently — status alone isn't a valid prefix:
SELECT * FROM orders WHERE status = 'pending';
```

Order columns by how the table is actually queried, not alphabetically
or by creation order.

## Partial indexes

An index with a `WHERE` clause, sized only for the rows that match it —
useful when queries consistently filter to a small, known subset:

```sql
CREATE INDEX ON orders (created_at) WHERE status = 'pending';
```

This only helps a query whose `WHERE` clause implies the index's
predicate (e.g. `WHERE status = 'pending' AND ...`) — it's not a general
index on `created_at` for all rows.

## Covering indexes (`INCLUDE`)

Adding non-key columns to an index (PostgreSQL 11+) lets some queries be
answered from the index alone, without visiting the table (an
"index-only scan"):

```sql
CREATE INDEX ON orders (customer_id) INCLUDE (status, total);
```

Worth it when a query's `SELECT` list is narrow and stable, and you've
confirmed via `EXPLAIN` that it isn't already getting an index-only scan.

## Building an index without blocking writes

Plain `CREATE INDEX` takes a lock that blocks writes to the table for the
duration of the build. On a production table with any meaningful size,
use `CONCURRENTLY` instead:

```sql
CREATE INDEX CONCURRENTLY ON orders (customer_id);
```

Tradeoffs: it takes longer overall, cannot run inside an explicit
transaction block, and can leave behind an invalid index if it fails
partway (`DROP INDEX` the invalid one and retry) — but it doesn't block
concurrent writes. The same `CONCURRENTLY` option exists for `DROP INDEX
CONCURRENTLY`.

## Common mistakes

- Adding an index without a specific query pattern it serves — see
  [AGENTS.md](../AGENTS.md#8-database-design-rules).
- Composite index column order that doesn't match how the table is
  actually filtered/sorted.
- Running plain `CREATE INDEX` (not `CONCURRENTLY`) against a production
  table, blocking writes for the build's duration.
- Assuming a partial index helps a query whose `WHERE` clause doesn't
  match its predicate.

## Quick revision

- B-tree by default; GIN for full-text/JSONB/array containment; BRIN for
  huge, naturally-ordered tables.
- Composite index columns must be queried left-to-right from the start
  to be used.
- `CONCURRENTLY` for building/dropping an index on a live production
  table.
- Every index needs a query pattern that justifies it.
