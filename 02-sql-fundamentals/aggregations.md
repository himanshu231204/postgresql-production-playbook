# Aggregations

## What it is

Computing a single value (count, sum, average, ...) across a group of
rows with `GROUP BY` and aggregate functions.

## Why it matters

Reporting, dashboards, and usage/cost metrics (including LLM token/cost
tracking — see [11-agentic-ai/](../11-agentic-ai/)) are almost all
aggregation queries.

## Syntax

```sql
SELECT col, count(*), sum(amount), avg(amount)
FROM table
WHERE condition        -- filters rows BEFORE aggregation
GROUP BY col
HAVING count(*) > 1;   -- filters groups AFTER aggregation
```

## `WHERE` vs `HAVING`

`WHERE` runs before grouping — it can't reference an aggregate.
`HAVING` runs after grouping — it filters on the aggregate result.
Using `WHERE` when you meant `HAVING` (or vice versa) either errors
(referencing an aggregate in `WHERE`) or silently computes the aggregate
over the wrong set of rows.

## Common aggregate functions

| Function | Notes |
|---|---|
| `count(*)` | Counts rows, including ones with `NULL` columns |
| `count(col)` | Counts rows where `col` is not `NULL` — **different result from `count(*)` when `col` has nulls** |
| `sum`, `avg`, `min`, `max` | Ignore `NULL` values |
| `array_agg(col)` | Collect values into a PostgreSQL array |
| `string_agg(col, ', ')` | Concatenate text values with a separator |
| `jsonb_agg(col)` | Collect values into a JSONB array |

## `FILTER` — conditional aggregation

```sql
SELECT
  count(*) AS total,
  count(*) FILTER (WHERE status = 'completed') AS completed,
  count(*) FILTER (WHERE status = 'failed') AS failed
FROM orders;
```

`FILTER (WHERE ...)` on an aggregate computes it over only the matching
rows, in one pass — clearer and often faster than the classic
`sum(CASE WHEN ... THEN 1 ELSE 0 END)` pattern.

## The functional-dependency exception

PostgreSQL allows selecting a column that isn't in `GROUP BY` if it's
functionally dependent on a grouped column — in practice, this means
grouping by a table's primary key lets you select any other column of
that same table without listing it in `GROUP BY`, since the primary key
already determines those values uniquely:

```sql
-- Valid: id is the primary key of users, so name is functionally determined by it.
SELECT id, name, count(*) FROM orders o JOIN users u ON u.id = o.user_id GROUP BY u.id;
```

## Common mistakes

- Confusing `count(*)` and `count(col)` when `col` can be `NULL` — they
  give different answers.
- Putting an aggregate condition in `WHERE` instead of `HAVING`.
- Using `sum(CASE WHEN ...)` when `FILTER (WHERE ...)` says the same thing
  more clearly.

## Performance considerations

`GROUP BY` on an unindexed column over a large table requires a full scan
plus a sort or hash aggregate — see
[05-performance/explain.md](../05-performance/explain.md) to check which
plan PostgreSQL chose. A materialized view (not covered yet in this repo)
is a common way to precompute an expensive, frequently-run aggregation.

## AI/agentic use case

Aggregating `model_usage` by model/day for cost tracking, or
`agent_runs`/`tool_calls` by status for success-rate monitoring, are
direct applications of `GROUP BY` + `FILTER`. See
[11-agentic-ai/](../11-agentic-ai/).

## Quick revision

- `WHERE` filters rows first; `HAVING` filters groups after aggregation.
- `count(*)` counts rows; `count(col)` skips `NULL`s in `col`.
- `FILTER (WHERE ...)` beats `CASE WHEN` for conditional aggregates.
- Grouping by a primary key lets you select that table's other columns
  ungrouped.
