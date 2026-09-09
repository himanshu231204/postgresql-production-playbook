# SQL Fundamentals

## What it is

The core SQL used in production application and reporting queries against
PostgreSQL: querying, writing, joining, aggregating, structuring queries
with CTEs and subqueries, and window functions.

## Why it matters

Everything downstream — performance tuning, ORM behavior, migrations,
agentic-AI retrieval — sits on top of queries written here. A wrong
`LEFT JOIN` filter or a `NOT IN` with a stray `NULL` produces wrong answers
silently; there's no error to catch it.

## In this section

| Page | Covers |
|---|---|
| [select.md](select.md) | `SELECT`, filtering, sorting, pagination |
| [insert-update-delete.md](insert-update-delete.md) | `INSERT`, `UPDATE`, `DELETE`, `UPSERT`, `RETURNING` |
| [joins.md](joins.md) | `INNER`/`LEFT`/`RIGHT`/`FULL`/`CROSS` joins, `LATERAL` |
| [aggregations.md](aggregations.md) | `GROUP BY`, `HAVING`, aggregate functions, `FILTER` |
| [cte.md](cte.md) | `WITH`, recursive CTEs, `MATERIALIZED`/`NOT MATERIALIZED` |
| [subqueries.md](subqueries.md) | Scalar/`IN`/`EXISTS` subqueries, correlated vs. uncorrelated |
| [window-functions.md](window-functions.md) | `OVER (PARTITION BY ...)`, ranking, `LAG`/`LEAD` |

## Where to go next

- Need the bare syntax with no explanation? See
  [16-command-reference/sql.md](../16-command-reference/sql.md) — a flat
  lookup table; this section is where the "why" and the gotchas live.
- Designing the tables these queries run against? See
  [03-database-design/](../03-database-design/).
- Query running slow? See [05-performance/](../05-performance/), starting
  with `EXPLAIN ANALYZE`.
- Need transaction semantics (isolation, locking) around these
  statements? See [04-transactions/](../04-transactions/).
