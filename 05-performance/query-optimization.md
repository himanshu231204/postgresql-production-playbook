# Query Optimization

## What it is

Fixing the *shape* of a query or the schema around it, once
[explain.md](explain.md) has shown you what's actually slow.

## Why it matters

Per [AGENTS.md](../AGENTS.md#9-performance-rules), "add an index and it
will be faster" is not a real answer. Most recurring performance
problems are one of a small number of query-shape issues — recognizing
them is faster than guessing.

## Workflow

1. Get the real, actual plan with `EXPLAIN (ANALYZE, BUFFERS)` — see
   [explain.md](explain.md).
2. Find the node(s) whose cost or actual time dominates the plan — not
   necessarily the top-level total.
3. Check whether that node's estimate matches reality; if not, see
   [analyze.md](analyze.md) before changing anything else.
4. Only then consider a schema/index/query-shape change, and re-run
   `EXPLAIN ANALYZE` to confirm it actually helped.

There's no universal "this many milliseconds is too slow" rule — compare
a query's plan and timing against its own prior baseline and against
what the business actually needs from it, not a number copied from
somewhere else.

## Common query-shape problems

### N+1 queries

Running one query to fetch a list, then one additional query per row to
fetch related data — common with ORMs that lazy-load relationships by
default:

```
SELECT * FROM orders WHERE customer_id = 1;         -- 1 query
SELECT * FROM order_items WHERE order_id = 101;      -- then N more,
SELECT * FROM order_items WHERE order_id = 102;      -- one per order
...
```

Fix by fetching the related data in one query instead — a `JOIN` (see
[02-sql-fundamentals/joins.md](../02-sql-fundamentals/joins.md)) or an
ORM's explicit eager-load option. See
[08-python-fastapi/](../08-python-fastapi/) for the SQLAlchemy-specific
patterns that cause and fix this.

### A function on the filtered column prevents index use

```sql
-- Won't use a plain index on email — the planner can't know
-- lower(email) matches the index without a matching expression index.
SELECT * FROM users WHERE lower(email) = 'a@example.com';

-- Fix: an expression index that matches exactly what the query computes
CREATE INDEX ON users (lower(email));
```

The same applies to any function or operation applied to the column
inside the `WHERE` clause — the index has to be built on the same
expression the query filters on.

### An implicit type cast breaks index use

Comparing a column to a literal of a different type can silently prevent
an index from being used if PostgreSQL has to cast the column (not the
literal) to compare them. Match the literal's type to the column's
declared type explicitly rather than relying on implicit coercion.

### Pagination that gets slower on later pages

`OFFSET`-based pagination scans and discards every skipped row — see
[02-sql-fundamentals/select.md](../02-sql-fundamentals/select.md#production-usage)
for the keyset-pagination fix.

### A wide `SELECT *` when an index-only scan was possible

Selecting only the columns actually needed can let the planner satisfy
a query entirely from an index, skipping the table — see
[03-database-design/indexes.md](../03-database-design/indexes.md#covering-indexes-include).

## Common mistakes

- Adding an index before confirming, with `EXPLAIN`, what's actually
  slow about the query.
- Fixing a query in isolation with hard-coded values, then finding the
  real, parameterized application query has a different plan (e.g. the
  planner made different assumptions about a bound parameter's
  selectivity).
- Chasing a specific numeric latency target from a blog post or another
  team's system instead of your own query's own before/after comparison.

## AI/agentic use case

A RAG pipeline's retrieval step is a normal SQL/pgvector query and gets
the same treatment — profile it with `EXPLAIN ANALYZE` rather than
assuming vector search is automatically fast. See
[10-pgvector/](../10-pgvector/).

## Quick revision

- Diagnose with `EXPLAIN (ANALYZE, BUFFERS)` before changing anything.
- N+1 queries, functions/casts on filtered columns, and `OFFSET`
  pagination are the most common recurring query-shape problems.
- Compare against your own baseline — there's no universal "slow"
  threshold.
