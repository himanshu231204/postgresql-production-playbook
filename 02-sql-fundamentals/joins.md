# JOINs

## What it is

Combining rows from two or more tables based on a related column.

## Why it matters

Almost every non-trivial query joins something. The most common source of
subtly wrong results in this repository's experience is filtering the
"outer" side of a `LEFT JOIN` in the wrong clause.

## Syntax

```sql
SELECT ...
FROM a
[INNER] JOIN b ON a.id = b.a_id
LEFT [OUTER] JOIN c ON a.id = c.a_id
RIGHT [OUTER] JOIN d ON a.id = d.a_id
FULL [OUTER] JOIN e ON a.id = e.a_id
CROSS JOIN f;
```

`JOIN ... USING (col)` is shorthand for `ON a.col = b.col` when the column
name is identical on both sides.

## Join types

| Type | Returns |
|---|---|
| `INNER JOIN` | Only rows with a match on both sides |
| `LEFT JOIN` | All rows from the left table, matched columns from the right (`NULL` where no match) |
| `RIGHT JOIN` | Mirror of `LEFT JOIN` — rarely used; a `LEFT JOIN` with tables swapped is more common style |
| `FULL JOIN` | All rows from both sides, `NULL` on whichever side has no match |
| `CROSS JOIN` | Every combination of rows from both sides (Cartesian product) |

## `LATERAL` joins

A PostgreSQL/SQL-standard feature: a `LATERAL` subquery can reference
columns from preceding `FROM` items — ordinary subqueries can't. Common
use: "top N rows per group."

```sql
SELECT c.id AS customer_id, o.id AS order_id, o.total
FROM customers c
CROSS JOIN LATERAL (
  SELECT id, total FROM orders o
  WHERE o.customer_id = c.id
  ORDER BY o.created_at DESC
  LIMIT 3
) o;
```

## Common mistakes

- **Filtering a `LEFT JOIN`'s right-side table in `WHERE` instead of
  `ON`.** This silently turns the `LEFT JOIN` into an `INNER JOIN`:

  ```sql
  -- WRONG: drops customers with no orders, defeating the LEFT JOIN
  SELECT c.id, o.id
  FROM customers c
  LEFT JOIN orders o ON c.id = o.customer_id
  WHERE o.status = 'completed';

  -- RIGHT: keep customers with no matching order (o.* becomes NULL)
  SELECT c.id, o.id
  FROM customers c
  LEFT JOIN orders o ON c.id = o.customer_id AND o.status = 'completed';
  ```

- Forgetting the join condition entirely — produces an accidental
  `CROSS JOIN` (every row × every row), which can silently return a huge,
  wrong result set instead of erroring.
- Joining on columns of different types (e.g. `text` vs `uuid`) that
  happen to cast implicitly — slower, and a sign the schema's types don't
  actually match.

## Performance considerations

The planner picks a nested loop, hash join, or merge join per join
depending on table sizes, available indexes, and estimated row counts —
you don't choose the algorithm directly. What you control is giving it
good inputs: indexes on join columns, and accurate statistics
(`ANALYZE`). See [05-performance/explain.md](../05-performance/explain.md)
to see which algorithm was actually chosen and why.

## AI/agentic use case

Joining `conversations` → `messages` → `tool_calls` is the standard shape
for reconstructing an agent run's full history. See
[11-agentic-ai/](../11-agentic-ai/).

## Quick revision

- Filter conditions on the "preserved" side of an outer join belong in
  `WHERE`; filter conditions on the "optional" side belong in `ON`.
- A missing join condition silently becomes a `CROSS JOIN`.
- `LATERAL` lets a subquery reference earlier `FROM` items — use it for
  top-N-per-group.
