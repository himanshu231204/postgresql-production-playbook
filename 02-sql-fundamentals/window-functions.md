# Window Functions

## What it is

Functions computed across a set of rows related to the current row
(a "window"), without collapsing those rows the way `GROUP BY` does.

## Why it matters

Window functions are the right tool for ranking, running totals, and
"compare this row to the previous/next row" — problems that are awkward
or slow with self-joins or correlated subqueries.

## Syntax

```sql
function_name(...) OVER (
  [PARTITION BY col, ...]
  [ORDER BY col, ...]
  [frame_clause]
)
```

`PARTITION BY` splits rows into independent groups (like `GROUP BY`, but
without collapsing rows). `ORDER BY` inside `OVER` defines row order
within each partition, for ranking and `LAG`/`LEAD`.

## Common window functions

| Function | Purpose |
|---|---|
| `row_number()` | Sequential number per partition, no ties |
| `rank()` | Rank with gaps after ties (1, 2, 2, 4) |
| `dense_rank()` | Rank without gaps after ties (1, 2, 2, 3) |
| `ntile(n)` | Divide partition into `n` roughly-equal buckets |
| `lag(col, n)` / `lead(col, n)` | Value from `n` rows before/after the current row |
| `first_value(col)` / `last_value(col)` | First/last value in the current frame |
| `sum(col) OVER (...)`, `avg(col) OVER (...)` | Running/partitioned aggregate, without collapsing rows |

## Example: top N per group

PostgreSQL has no `QUALIFY` clause (unlike some other databases), so
filtering on a window function's result needs a subquery or CTE:

```sql
SELECT * FROM (
  SELECT *, row_number() OVER (PARTITION BY customer_id ORDER BY created_at DESC) AS rn
  FROM orders
) ranked
WHERE rn <= 3;   -- most recent 3 orders per customer
```

## Example: running total

```sql
SELECT order_date, amount,
       sum(amount) OVER (ORDER BY order_date) AS running_total
FROM orders;
```

## The frame-clause default that surprises people

The default frame depends on whether `ORDER BY` is present inside `OVER`:

- **With `ORDER BY`:** the default frame is `RANGE BETWEEN UNBOUNDED
  PRECEDING AND CURRENT ROW` — an aggregate like `sum(...) OVER (ORDER BY
  ...)` becomes a *running* total up to the current row, not a total over
  the whole partition.
- **Without `ORDER BY`:** the default frame is the entire partition, so
  the same aggregate becomes a partition-wide total instead of a running
  one.

Adding `ORDER BY` to get ranking right, without realizing it also changes
an aggregate's default frame in the same `OVER (...)`, is a common source
of a "why is my running total wrong" bug. Be explicit when it matters:

```sql
sum(amount) OVER (ORDER BY order_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)  -- explicit running total
sum(amount) OVER ()  -- explicit partition-wide total, no ORDER BY needed
```

`ROWS`, `RANGE`, and `GROUPS` (PostgreSQL 11+) frame modes differ in how
they handle peer rows (ties on the `ORDER BY` value) — `ROWS` counts
physical rows, `RANGE`/`GROUPS` count logical peer groups.

## Common mistakes

- Confusing `rank()` and `dense_rank()` when there are ties.
- Not realizing `ORDER BY` inside `OVER (...)` changes an aggregate's
  default frame from "whole partition" to "running up to current row."
- Trying to filter directly on a window function in `WHERE` — window
  functions can't be used there; wrap the query in a subquery/CTE and
  filter in the outer `WHERE`, as shown above.

## Performance considerations

Each distinct `PARTITION BY`/`ORDER BY` combination in a query typically
requires its own sort — multiple window functions with different
`PARTITION BY`/`ORDER BY` clauses cost more than ones that share the same
one. Check [05-performance/explain.md](../05-performance/explain.md) for
the `WindowAgg`/`Sort` nodes in the plan.

## AI/agentic use case

`row_number() OVER (PARTITION BY idempotency_key ORDER BY created_at)` is
a direct way to detect/deduplicate retried `tool_calls` rows sharing the
same idempotency key, keeping only `rn = 1`. See
[AGENTS.md](../AGENTS.md#12-agentic-ai-database-rules).

## Quick revision

- `PARTITION BY` groups without collapsing rows; `ORDER BY` inside `OVER`
  sets ranking/frame order.
- `ORDER BY` inside `OVER` changes an aggregate's default frame to a
  running calculation — be explicit with `ROWS BETWEEN ...` if that's not
  what you want.
- No `QUALIFY` in PostgreSQL — filter a window function's result via an
  outer `WHERE` on a subquery/CTE.
