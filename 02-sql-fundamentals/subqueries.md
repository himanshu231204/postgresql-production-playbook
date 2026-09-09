# Subqueries

## What it is

A `SELECT` nested inside another statement — as a scalar value, inside
`WHERE`/`IN`/`EXISTS`, or as a derived table in `FROM`.

## Why it matters

`NOT IN` has a well-known correctness trap with `NULL` values that
silently returns zero rows instead of erroring — worth knowing before it
costs you a debugging session.

## Syntax

```sql
-- Scalar subquery: must return exactly one row, one column
SELECT name, (SELECT max(total) FROM orders WHERE customer_id = c.id) AS max_order
FROM customers c;

-- IN
SELECT * FROM customers WHERE id IN (SELECT customer_id FROM orders WHERE total > 1000);

-- EXISTS
SELECT * FROM customers c
WHERE EXISTS (SELECT 1 FROM orders o WHERE o.customer_id = c.id AND o.total > 1000);

-- Derived table (subquery in FROM)
SELECT avg(order_count) FROM (
  SELECT customer_id, count(*) AS order_count FROM orders GROUP BY customer_id
) per_customer;
```

## Correlated vs. uncorrelated

A subquery that references a column from the outer query (like `c.id`
above) is **correlated** — conceptually re-evaluated per outer row. One
that stands alone is **uncorrelated** — evaluated once. `EXISTS` and
scalar subqueries are typically correlated; a subquery used with `IN` is
often uncorrelated.

## The `NOT IN` / `NULL` trap

```sql
-- If ANY customer_id in orders is NULL, this returns ZERO rows —
-- not "customers with no orders over $1000", but nothing at all.
SELECT * FROM customers
WHERE id NOT IN (SELECT customer_id FROM orders WHERE total > 1000);
```

This happens because SQL's `NOT IN` is defined via `<> ALL (...)`, and
`x <> NULL` evaluates to `UNKNOWN`, not `TRUE` — a single `NULL` in the
subquery's result poisons the whole comparison. `NOT EXISTS` doesn't have
this problem:

```sql
-- Correct and NULL-safe:
SELECT * FROM customers c
WHERE NOT EXISTS (
  SELECT 1 FROM orders o WHERE o.customer_id = c.id AND o.total > 1000
);
```

**Prefer `EXISTS`/`NOT EXISTS` over `IN`/`NOT IN` with subqueries** —
they're NULL-safe and typically at least as fast, since PostgreSQL can
stop as soon as one matching row is found.

## Common mistakes

- Using `NOT IN` against a subquery column that can contain `NULL`.
- Writing a correlated subquery in `SELECT`'s column list when a `JOIN`
  would compute the same result once instead of per row — check
  `EXPLAIN ANALYZE` if a query with a scalar subquery is slow.
- Forgetting a scalar subquery must return exactly one row — it errors at
  runtime if it returns more than one.

## Performance considerations

A correlated subquery conceptually runs once per outer row; PostgreSQL's
planner can often rewrite it into a join internally, but not always.
Check [05-performance/explain.md](../05-performance/explain.md) if a query
built from subqueries is slow — rewriting it as an explicit `JOIN` or CTE
is a common fix when the planner didn't optimize it well.

## Quick revision

- `EXISTS`/`NOT EXISTS` over `IN`/`NOT IN` when the subquery's column can
  contain `NULL`.
- A scalar subquery must return exactly one row, one column.
- Check `EXPLAIN ANALYZE` before assuming a subquery-heavy query needs a
  rewrite.
