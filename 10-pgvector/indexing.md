# pgvector Indexing (HNSW and IVFFlat)

This page covers **vector** indexes. General index design (B-tree, GIN,
partial, covering) is in [03-database-design/indexes.md](../03-database-design/indexes.md);
monitoring index usage is in [05-performance/indexes.md](../05-performance/indexes.md).

## What it is

Approximate nearest-neighbor (ANN) indexes that trade some recall for speed.
pgvector provides two: **HNSW** (multilayer graph) and **IVFFlat** (inverted
lists over clusters). With no index, queries are exact.

## Why it matters

Per [AGENTS.md](../AGENTS.md#8-database-design-rules) every index costs
writes and storage. Vector indexes also cost **memory** (builds and caches)
and change **query results**. An index is justified only when exact search is
too slow for your row count and latency target, and recall stays acceptable.

## HNSW vs. IVFFlat

| | HNSW | IVFFlat |
|---|---|---|
| Structure | Multilayer graph | Lists (clusters); queries scan the nearest `probes` lists |
| Speed-recall tradeoff | Better | Lower |
| Build time | Slower | Faster |
| Memory use | Higher | Lower |
| Needs data before build | No (can be built on an empty table) | Yes (lists are trained from existing rows) |
| Main query knob | `hnsw.ef_search` (default 40) | `ivfflat.probes` (default 1) |
| Main build knobs | `m` (16), `ef_construction` (64) | `lists` |
| Max dims indexed (`vector`) | 2,000 | 2,000 |

Source: pgvector README. Neither is "the correct choice": choose HNSW when
query speed/recall matters and you can afford build time and RAM; choose
IVFFlat when build time/memory dominate or you rebuild often, and accept
lower recall at a given speed. Benchmark both on your data.

## HNSW

```sql
CREATE INDEX CONCURRENTLY chunks_embedding_hnsw
    ON chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
```

Serves `ORDER BY embedding <=> $1 LIMIT k`. Tradeoff: faster approximate
queries vs. slower inserts (each row updates the graph), more disk/RAM, and
long builds on big tables.

| Parameter | Default | Effect |
|---|---|---|
| `m` | 16 | Max connections per layer. Higher: better recall, larger index, slower build |
| `ef_construction` | 64 | Candidate list size while building. Higher: better recall, slower build/insert |
| `hnsw.ef_search` (query-time) | 40 | Candidate list size per query. Higher: better recall, slower query. Also caps how many rows an index scan can return |

Use the defaults unless you measure low recall. Set `ef_search` per
transaction:

```sql
BEGIN;
SET LOCAL hnsw.ef_search = 100;
SELECT id FROM chunks ORDER BY embedding <=> $1 LIMIT 10;
COMMIT;
```

`ef_search` must be at least `LIMIT` for the index to return that many rows.

## IVFFlat

```sql
-- build AFTER loading representative data
CREATE INDEX CONCURRENTLY chunks_embedding_ivf
    ON chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

SET ivfflat.probes = 10;   -- per session or SET LOCAL per transaction
```

Three keys from the pgvector README:

1. Create the index **after** the table has data. Lists are chosen from the
   existing rows; building on an empty or unrepresentative table gives poor recall
   (rebuild after large data shifts).
2. Choose `lists`. Starting points from the pgvector README: `rows / 1000`
   up to 1M rows, `sqrt(rows)` above that.
3. Choose `probes`. Starting point: `sqrt(lists)`. Higher = better recall,
   slower. Setting `probes` equal to `lists` is exact search and the planner
   will not use the index.

These are starting points to tune, not rules; confirm with a recall test
([similarity-search.md](similarity-search.md#measuring-recall)).

## Build memory and parallelism

HNSW builds are significantly faster when the graph fits in
`maintenance_work_mem`. If it does not, PostgreSQL emits:

```text
NOTICE:  hnsw graph no longer fits into maintenance_work_mem after N tuples
```

Raise it for the build session only, and do not exhaust server RAM:

```sql
SET maintenance_work_mem = '2GB';              -- size to your instance
SET max_parallel_maintenance_workers = 4;      -- plus the leader; may need max_parallel_workers raised
CREATE INDEX CONCURRENTLY ...;
```

Load initial data first and index afterward; bulk loading into an already
indexed table is slower.

## Building safely in production

- `CREATE INDEX` blocks writes to the table for the whole build. Use
  `CREATE INDEX CONCURRENTLY` on a live table (slower, two passes, cannot run
  inside a transaction block; validated on 0.8.1). A failed concurrent build
  leaves an `INVALID` index that you must drop and retry:

```sql
SELECT indexrelid::regclass FROM pg_index WHERE NOT indisvalid;
DROP INDEX CONCURRENTLY chunks_embedding_hnsw;   -- destructive to that index only; confirm the name first
```

- Watch progress:

```sql
SELECT phase, round(100.0 * blocks_done / nullif(blocks_total, 0), 1) AS pct
FROM pg_stat_progress_create_index;
```

- Replacing an index: build the new one `CONCURRENTLY`, verify with
  `EXPLAIN`, then `DROP INDEX CONCURRENTLY` the old one.
- Expect build time and RAM to scale with rows and dimensions; test on a
  production-sized copy before scheduling.

## Filtering and indexes

Approximate indexes apply `WHERE` **after** the index scan, so restrictive
filters can return fewer than `LIMIT` rows. Options (see the table in
[similarity-search.md](similarity-search.md#metadata-filtering)):

```sql
-- partial index: few known values; queries must repeat the predicate
CREATE INDEX ON chunks USING hnsw (embedding vector_cosine_ops)
    WHERE (category = 'security');

-- partitioning: many values / tenant isolation
CREATE TABLE chunks (
    id BIGINT GENERATED ALWAYS AS IDENTITY,
    tenant_id INTEGER NOT NULL,
    embedding vector(384) NOT NULL
) PARTITION BY LIST (tenant_id);
```

Validated: on 0.8.1 a partial HNSW index on `WHERE category_id = 2` was
chosen by the planner for a query repeating that predicate. A shared
approximate index across tenants lets one tenant's vectors affect another's
recall and speed (pgvector README); use list partitioning or separate
tables for isolation.

## Iterative index scans (pgvector 0.8.0+)

When filtering leaves too few rows, iterative scans keep scanning the index
until enough rows are found or a limit is hit.

```sql
SET hnsw.iterative_scan = strict_order;    -- exact distance order
-- or relaxed_order: better recall, results may be slightly out of order
SET ivfflat.iterative_scan = relaxed_order; -- IVFFlat supports relaxed_order
```

| Setting | Default | Meaning |
|---|---|---|
| `hnsw.max_scan_tuples` | 20,000 | Max tuples visited (approximate; excludes the initial scan) |
| `hnsw.scan_mem_multiplier` | 1 | Max scan memory as a multiple of `work_mem` |
| `ivfflat.max_probes` | | Max probes during iterative scans |

Defaults confirmed on 0.8.1 for `hnsw.max_scan_tuples` (`SHOW` returned
20000). Tradeoff: better filtered recall, but a rare filter can scan a large
part of the index and be slow. Bound it with `max_scan_tuples` and test the
worst-case filter value. On pgvector versions before 0.8.0 these settings do
not exist; use partial indexes, partitions, or higher `ef_search`/`probes`.

## Maintenance

- **Inserts/updates/deletes**: HNSW and IVFFlat are updated on write. IVFFlat
  list centroids are not retrained; after large data changes, `REINDEX INDEX CONCURRENTLY`.
- **Vacuum**: vacuuming HNSW indexes can be slow; the pgvector README suggests
  `REINDEX INDEX CONCURRENTLY index_name;` before `VACUUM table_name;`. See
  [05-performance/vacuum.md](../05-performance/vacuum.md).
- **Size**: `SELECT pg_size_pretty(pg_relation_size('chunks_embedding_hnsw'));`
- **Keep the index in memory** where you can: ANN queries touch scattered
  pages. If the index outgrows RAM, options are `halfvec`, binary
  quantization with re-ranking, vertical scaling, replicas, or a different system.

## When pgvector indexing is not enough

Very large corpora relative to node memory, strict latency at high QPS with
heavy filters, or vector workloads that would starve your OLTP queries are
cases where a dedicated vector database (or isolating vectors on their own
PostgreSQL instance/replica) can be the better tradeoff. If transactional
consistency with relational data and operational simplicity are the priority,
pgvector's single-system advantage is usually decisive. Decide with
measurements.

## Common mistakes

- Building IVFFlat on an empty table, then wondering about poor recall.
- Index operator class not matching the query operator.
- Raising `ef_search`/`probes` globally instead of per transaction.
- Plain `CREATE INDEX` on a live table (blocks writes), or a huge
  `maintenance_work_mem` times several sessions exhausting RAM.
- Declaring victory because `EXPLAIN` shows an index scan, without measuring recall.
- Adding both an HNSW and an IVFFlat index on one column "just in case"; each costs writes and storage. Add one index per metric you query.

## Troubleshooting

| Symptom | Check |
|---|---|
| Index not used | `EXPLAIN`; operator/opclass mismatch; no `LIMIT`; `DESC` ordering; tiny table |
| Fewer than `LIMIT` rows with a `WHERE` | Post-filtering; iterative scans (0.8.0+), partial index, partitions, higher `ef_search`/`probes` |
| Low recall | Compare to exact search; raise `ef_search`/`probes`; for IVFFlat, rebuild on current data and re-tune `lists` |
| Slow build | `maintenance_work_mem`, parallel workers, build after bulk load; watch the NOTICE |
| Invalid index after failed build | `pg_index.indisvalid`; drop and retry |

## Quick revision

- One index per metric; opclass must match the operator.
- HNSW: better speed-recall, slower build, more memory. IVFFlat: faster build, less memory, lower recall; build after loading data.
- Tune `hnsw.ef_search` / `ivfflat.probes` per transaction with `SET LOCAL`.
- Filtered queries are post-filtered; iterative scans need 0.8.0+.
- Build with `CONCURRENTLY`; measure recall against exact search.
