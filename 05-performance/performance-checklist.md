# Performance Checklist

A scannable set of checks, not pass/fail numeric thresholds — compare
each against your own system's baseline, not a number from elsewhere
(see [AGENTS.md](../AGENTS.md#9-performance-rules)).

## Before shipping a new query or feature

- [ ] Ran `EXPLAIN (ANALYZE, BUFFERS)` on the actual query the
      application issues, not a hand-simplified version — see
      [explain.md](explain.md).
- [ ] Checked whether the plan's estimated row counts roughly match the
      actual counts; if not, ran `ANALYZE` before drawing conclusions —
      see [analyze.md](analyze.md).
- [ ] Confirmed an index exists for the query's actual filter/sort
      columns, in the order the query uses them — see
      [03-database-design/indexes.md](../03-database-design/indexes.md).
- [ ] Checked for N+1 query patterns if the code path goes through an
      ORM — see [query-optimization.md](query-optimization.md#n1-queries).
- [ ] Used keyset pagination instead of `OFFSET` if the result set can
      grow large — see
      [02-sql-fundamentals/select.md](../02-sql-fundamentals/select.md#production-usage).
- [ ] Wrapped multi-step writes in a transaction sized to hold locks for
      as short a time as possible — see
      [04-transactions/transactions.md](../04-transactions/transactions.md#performance-considerations).

## Before a production deploy that changes schema or query volume

- [ ] Any new index on an existing table was built with `CREATE INDEX
      CONCURRENTLY` — see
      [03-database-design/indexes.md](../03-database-design/indexes.md#building-an-index-without-blocking-writes).
- [ ] Any new constraint/foreign key on an existing table used `NOT
      VALID` + `VALIDATE CONSTRAINT` — see
      [03-database-design/foreign-keys.md](../03-database-design/foreign-keys.md#production-considerations).
- [ ] A large bulk load is followed by a manual `ANALYZE`, not left to
      autovacuum's next cycle — see [analyze.md](analyze.md#when-to-run-it-manually).
- [ ] Connection usage is pooled appropriately for the expected
      concurrency increase — see [connection-pooling.md](connection-pooling.md).

## Ongoing / periodic

- [ ] Checked `pg_stat_user_indexes` for indexes with `idx_scan = 0`
      that no longer serve any query pattern — see
      [indexes.md](indexes.md#finding-unused-indexes).
- [ ] Checked `pg_stat_user_tables` for a rising `seq_scan` count on a
      large, growing table — see [indexes.md](indexes.md#finding-a-missing-index).
- [ ] Confirmed autovacuum is keeping up on high-churn tables (not
      falling behind, causing bloat) — see [vacuum.md](vacuum.md#autovacuum).
- [ ] Reviewed slow-query logs/`pg_stat_statements` for queries that
      have gotten slower over time, not just ones that are slow in
      isolation — see [14-observability/slow-queries.md](../14-observability/slow-queries.md).

## If something is slow right now

Go straight to
[15-production-runbooks/slow-query.md](../15-production-runbooks/slow-query.md)
instead of working through this checklist from the top.
