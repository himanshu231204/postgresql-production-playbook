# ANALYZE and Planner Statistics

## What it is

The `ANALYZE` statement, which samples a table's data and records
statistics (value distribution, distinct-value estimates, null
fraction) that the query planner uses to choose a plan.

**Not to be confused with `EXPLAIN ANALYZE`** — same word, unrelated
purpose. `ANALYZE` updates statistics; `EXPLAIN ANALYZE` runs a query
and shows its plan. See [explain.md](explain.md).

## Why it matters

The planner doesn't know your data — it estimates based on statistics
gathered by `ANALYZE`. Stale statistics are one of the most common
reasons a query that used to be fast suddenly isn't: the planner is
still estimating based on how the table looked before it grew, shrank,
or changed shape.

## Syntax

```sql
ANALYZE orders;              -- one table
ANALYZE orders (customer_id); -- one column
ANALYZE;                      -- every table in the database
```

## Why the planner needs statistics at all

Given `WHERE status = 'pending'`, the planner needs to estimate *how
many* rows will match to decide whether a `Seq Scan` or an `Index Scan`
will be cheaper. That estimate comes from `pg_statistic` (populated by
`ANALYZE`), not from actually counting matching rows first — that would
defeat the purpose of planning.

## Autovacuum's automatic ANALYZE

Autovacuum runs `ANALYZE` automatically as tables change (governed by
`autovacuum_analyze_threshold`/`autovacuum_analyze_scale_factor`,
parallel to the vacuum thresholds in [vacuum.md](vacuum.md)). This
usually keeps statistics reasonably fresh without manual intervention.

## When to run it manually

- **Immediately after a bulk load** (`COPY`, a large batch `INSERT`, or
  restoring from a backup) — don't wait for autovacuum's next cycle
  when you're about to run queries against data whose shape the planner
  has never seen.
- After changing `default_statistics_target` for a specific column, to
  make the new sample size take effect immediately rather than waiting
  for the next automatic run.

## `default_statistics_target`

Controls how large a sample `ANALYZE` takes, and how many
most-common-values/histogram buckets it keeps per column — defaults to
`100`, and can be set anywhere from `1` to `10000`. Raise it per-column
(via `ALTER TABLE ... ALTER COLUMN ... SET STATISTICS n`) for
a specific column the planner keeps misjudging, such as one with a
highly skewed value distribution — this costs more time/space during
`ANALYZE` and slightly larger planning time in exchange for better
estimates.

## Common mistakes

- Assuming `ANALYZE` and `EXPLAIN ANALYZE` are related — they aren't;
  one updates statistics, the other executes and profiles a query.
- Bulk-loading data and immediately benchmarking query performance
  without running `ANALYZE` first — the planner is working from
  pre-load statistics.
- Raising `default_statistics_target` database-wide to fix one column's
  bad estimates, instead of targeting that column specifically.

## Troubleshooting

| Symptom | Check |
|---|---|
| `EXPLAIN`'s estimated rows are far from `EXPLAIN ANALYZE`'s actual rows | Statistics are likely stale — run `ANALYZE` on the table |
| A query got slower right after a large data change | Run `ANALYZE` before assuming a schema/index change is needed |

## Quick revision

- `ANALYZE` updates planner statistics; it is not `EXPLAIN ANALYZE`.
- Autovacuum runs it automatically, but not fast enough right after a
  bulk load — run it manually then.
- A large estimated-vs-actual row gap in `EXPLAIN ANALYZE` output points
  here before it points at the schema.
