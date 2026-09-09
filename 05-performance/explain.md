# EXPLAIN and EXPLAIN ANALYZE

## What it is

The tool that shows what the query planner decided to do — and,
with `ANALYZE`, what actually happened when it did it.

## Why it matters

Every performance question in this repository reduces to "what does
`EXPLAIN` say?" Guessing why a query is slow without looking at its plan
is how time gets wasted adding indexes that don't help.

## Syntax

```sql
EXPLAIN SELECT * FROM orders WHERE customer_id = 42;

EXPLAIN ANALYZE SELECT * FROM orders WHERE customer_id = 42;

EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT * FROM orders WHERE customer_id = 42;
```

| Form | What it does |
|---|---|
| `EXPLAIN` | Shows the planned execution plan and estimated costs — does **not** run the query |
| `EXPLAIN ANALYZE` | Actually **runs** the query, then shows the plan with real row counts and timings alongside the estimates |
| `EXPLAIN (ANALYZE, BUFFERS)` | Adds shared-buffer hit/read counts per node — tells you whether data came from cache or disk |

**`EXPLAIN ANALYZE` really executes the statement.** For `INSERT`/`UPDATE`/`DELETE`,
that means the write actually happens. To inspect the plan for a write
without keeping its effects:

```sql
BEGIN;
EXPLAIN ANALYZE UPDATE orders SET status = 'shipped' WHERE id = 1;
ROLLBACK;
```

## Reading a plan

Plans are trees, indented by nesting; PostgreSQL executes from the
innermost (most deeply indented) nodes outward. Each node shows:

```
Index Scan using orders_customer_id_idx on orders
  (cost=0.29..8.31 rows=1 width=64)
  (actual time=0.021..0.023 rows=1 loops=1)
```

| Field | Meaning |
|---|---|
| Node type | The operation — `Seq Scan`, `Index Scan`, `Index Only Scan`, `Bitmap Heap Scan`, `Nested Loop`, `Hash Join`, `Merge Join`, `Sort`, etc. |
| `cost=start..total` | The planner's *estimate*, in arbitrary internal units — useful for comparing nodes/plans against each other, not a time unit |
| `rows` (in `cost=...`) | Estimated rows this node will produce |
| `actual time=start..total` | Only with `ANALYZE` — real milliseconds elapsed |
| `actual ... rows=N loops=M` | Only with `ANALYZE` — real rows produced, and how many times this node executed (a nested loop's inner node runs once per outer row) |

## Common node types

| Node | What it means |
|---|---|
| `Seq Scan` | Reads the whole table. Fine for a small table or when most rows match; a red flag on a large table with a selective filter |
| `Index Scan` | Uses an index to find matching rows, then fetches each from the table | 
| `Index Only Scan` | Answers the query from the index alone, no table visit needed — see [03-database-design/indexes.md](../03-database-design/indexes.md#covering-indexes-include) |
| `Bitmap Heap Scan` / `Bitmap Index Scan` | Builds a bitmap of matching pages from one or more indexes, then visits them — common when a single index scan would match too many scattered rows to do one-by-one |
| `Nested Loop` | For each outer row, re-runs the inner node — cheap only when the outer side has few rows |
| `Hash Join` / `Merge Join` | Alternative join strategies for larger inputs |

## Common mistakes

- Reading `EXPLAIN` (without `ANALYZE`) and trusting the estimated row
  counts as fact — they come from planner statistics, which can be stale
  (see [analyze.md](analyze.md)).
- Comparing `cost` values across different queries as if they were
  comparable real time — they're only meaningful relative to other nodes
  in the *same* plan.
- Running `EXPLAIN ANALYZE` on a write statement in production without
  wrapping it in a transaction you intend to roll back.
- Fixating on the top-level total cost instead of finding which specific
  node is disproportionately expensive.

## Performance considerations

A large gap between a node's *estimated* and *actual* row count is one
of the strongest signals that planner statistics are stale — see
[analyze.md](analyze.md). A `Seq Scan` on a large table isn't
automatically wrong; check whether an index exists for that filter and,
if so, why the planner didn't choose it (stale statistics and a
non-selective filter are the two most common reasons).

## AI/agentic use case

Before assuming an agentic workload's slow query needs a schema change,
run `EXPLAIN ANALYZE` on the actual query the application issues (not a
simplified version) — ORMs and query builders can produce a materially
different query shape than what you'd write by hand.

## Quick revision

- `EXPLAIN` estimates; `EXPLAIN ANALYZE` actually runs the query.
- `cost` units are relative, not milliseconds — `actual time` (with
  `ANALYZE`) is.
- Wrap a write in `BEGIN; ... ROLLBACK;` to `EXPLAIN ANALYZE` it safely.
- A big estimated-vs-actual row gap points at stale statistics, not
  necessarily a missing index.
