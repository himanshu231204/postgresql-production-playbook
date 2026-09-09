# Indexes (Monitoring)

This page covers **monitoring existing indexes** — usage stats and
bloat. For choosing an index type/structure at design time (B-tree vs.
GIN vs. GiST vs. BRIN, composite/partial/covering indexes,
`CONCURRENTLY`), see
[03-database-design/indexes.md](../03-database-design/indexes.md) — that
page owns index design; this one owns watching indexes you already have.

## What it is

Views (`pg_stat_user_indexes`, `pg_stat_user_tables`) that track how much
an index is actually being used, so you can find indexes that cost
write overhead without earning their keep.

## Why it matters

Per [AGENTS.md](../AGENTS.md#8-database-design-rules), every index has an
ongoing write cost. An index added for a query pattern that never
materialized, or that got replaced by a different query shape later,
is pure cost with no benefit — and the only way to find it is to look.

## Finding unused indexes

```sql
SELECT
  schemaname, relname AS table_name, indexrelname AS index_name,
  idx_scan, idx_tup_read, idx_tup_fetch
FROM pg_stat_user_indexes
WHERE idx_scan = 0
ORDER BY pg_relation_size(indexrelid) DESC;
```

| Column | Meaning |
|---|---|
| `idx_scan` | Number of index scans that used this index since stats were last reset |
| `idx_tup_read` | Rows the index scan itself returned |
| `idx_tup_fetch` | Rows actually fetched from the table after that (0 for an index-only scan that didn't need to visit the table) |

`idx_scan = 0` on a database that's been running under real traffic for
a while is the clearest signal — but check how long stats have
accumulated (`pg_stat_reset()` clears them) and whether the index backs
a `UNIQUE`/primary-key constraint rather than a query pattern, since
constraint-backing indexes are worth keeping even with a low scan count.

## Finding a missing index

```sql
SELECT relname AS table_name, seq_scan, idx_scan,
       seq_tup_read, n_live_tup
FROM pg_stat_user_tables
ORDER BY seq_scan DESC;
```

A high `seq_scan` count relative to `idx_scan` on a large table
(`n_live_tup`) is worth investigating with `EXPLAIN` (see
[explain.md](explain.md)) — though a sequential scan on a small table,
or one that legitimately reads most of the table's rows, is not a
problem to fix.

## Index bloat

Like tables, indexes accumulate dead space as the rows they reference
are updated/deleted — see [vacuum.md](vacuum.md) for the mechanism.
A bloated index is larger on disk and in cache than it needs to be for
the data it actually indexes; `REINDEX` (or `REINDEX CONCURRENTLY` to
avoid blocking, mirroring `CREATE INDEX CONCURRENTLY`) rebuilds it from
scratch.

## Common mistakes

- Dropping an index just because `idx_scan` is low, without checking
  whether it backs a constraint or was only recently created.
- Assuming a high `seq_scan` count is automatically a problem — check
  what's actually being scanned and whether an index would help before
  adding one.
- Never revisiting index usage after shipping a feature that changed
  the query patterns an old index was built for.

## Quick revision

- `pg_stat_user_indexes.idx_scan = 0` → candidate for removal, after
  checking constraint-backing and stats-reset timing.
- `pg_stat_user_tables`: high `seq_scan` vs. `idx_scan` on a large table
  → investigate with `EXPLAIN`, don't index reflexively.
- Indexes bloat too — `REINDEX CONCURRENTLY` to reclaim space without
  blocking.
