# Performance

## What it is

How to find out *why* a query is slow, and what to do about it — reading
query plans, keeping planner statistics fresh, monitoring index
usefulness, understanding VACUUM/autovacuum, and connection pooling.

## Why it matters

"Add an index and it will be faster" is not an answer — it's a guess.
Every page in this section is about replacing guesses with evidence:
what the planner actually chose, why, and what changed it.

## In this section

| Page | Covers |
|---|---|
| [explain.md](explain.md) | `EXPLAIN`/`EXPLAIN ANALYZE`, reading a plan |
| [analyze.md](analyze.md) | The `ANALYZE` statement and planner statistics |
| [query-optimization.md](query-optimization.md) | Query shape problems: N+1, functions on indexed columns, implicit casts |
| [indexes.md](indexes.md) | Monitoring existing indexes: usage stats, unused indexes, bloat |
| [vacuum.md](vacuum.md) | MVCC dead tuples, `VACUUM` vs. `VACUUM FULL`, autovacuum |
| [connection-pooling.md](connection-pooling.md) | Why connections are expensive, `max_connections`, PgBouncer pool modes |
| [performance-checklist.md](performance-checklist.md) | A scannable pre-deploy/triage checklist |

## Where to go next

- Choosing an index type/structure at design time (not monitoring an
  existing one): see
  [03-database-design/indexes.md](../03-database-design/indexes.md).
- Locking and transaction-length effects on vacuum: see
  [04-transactions/](../04-transactions/).
- Configuring pooling from the application/SQLAlchemy side: see
  [08-python-fastapi/connection-pooling.md](../08-python-fastapi/connection-pooling.md).
- Live diagnostic queries (active connections, blocked queries): see
  [14-observability/](../14-observability/).
- Mid-incident, a query is suddenly slow right now: see
  [15-production-runbooks/slow-query.md](../15-production-runbooks/slow-query.md).
