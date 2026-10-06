# Runbook: Slow Query

Applies to PostgreSQL 16. Goal: find what is slow **right now**, stop it
from hurting everything else, then fix the cause with evidence.

## Symptoms

- API latency or timeouts up; endpoint-specific or global.
- Database CPU or I/O saturated; connection count rising (queries queue up and hold slots).
- One query (report, search, ORM-generated) running for minutes.
- A query that was fast yesterday is slow today (plan change, stale statistics, data growth).

## Triage (first 2 minutes)

SQL (needs `pg_monitor` or superuser to see everyone's queries):

```sql
SELECT pid, usename, application_name, state, wait_event_type, wait_event,
       now() - query_start AS runtime,
       left(query, 100)    AS query
FROM pg_stat_activity
WHERE state = 'active'
  AND backend_type = 'client backend'
  AND pid <> pg_backend_pid()
ORDER BY query_start;
```

Read `wait_event_type`:

| `wait_event_type` / `wait_event` | Meaning | Next |
|---|---|---|
| `Lock` (e.g. `transactionid`, `relation`, `tuple`) | Not slow: **blocked** | [lock-contention.md](lock-contention.md) |
| `IO` (e.g. `DataFileRead`) | Reading from disk: missing index, cold cache, or table too big for cache | [Diagnosis](#diagnosis) |
| `LWLock`, `BufferPin` | Internal contention (many concurrent writers/readers on hot pages) | Reduce concurrency; escalate if persistent |
| `Client` (`ClientRead`) | Waiting on the **client** (app is slow to send/read) | Look at the app, not the DB |
| `Timeout` / `PgSleep` | Sleeping (`pg_sleep`) | Expected for that statement |
| empty (on CPU) | Executing: bad plan, big scan, heavy sort/hash | [Diagnosis](#diagnosis) |

If many sessions run the **same** query, it is a hot-path regression. If one
long-runner dominates, it is a report or batch job.

Also check what changed: a deploy in the last hour, a new ORM query, a
batch started, a big data load, autovacuum falling behind.

## Diagnosis

### 1. Longest-running and oldest transactions (SQL)

```sql
SELECT pid, usename, application_name, state,
       now() - xact_start  AS xact_age,
       now() - query_start AS query_age,
       left(query, 100)    AS query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL AND backend_type = 'client backend'
ORDER BY xact_start
LIMIT 10;
```

A very old transaction also holds back vacuum (dead rows cannot be
removed), which slows *everything* over time. See
[05-performance/vacuum.md](../05-performance/vacuum.md).

### 2. Which queries cost the most overall: `pg_stat_statements` (SQL)

Requires the extension (`shared_preload_libraries = 'pg_stat_statements'`,
a restart, then `CREATE EXTENSION pg_stat_statements;` in the database).
Without it, use the log (step 5).

```sql
SELECT queryid, calls,
       round(total_exec_time::numeric, 1) AS total_ms,
       round(mean_exec_time::numeric, 2)  AS mean_ms,
       rows, shared_blks_read, temp_blks_written,
       left(query, 80) AS query
FROM pg_stat_statements
WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
ORDER BY total_exec_time DESC
LIMIT 10;
```

Sort by `total_exec_time` for "what consumes the server," by
`mean_exec_time` for "what is slowest per call." High `temp_blks_written`
means sorts/hashes spill to disk (`work_mem` too small for that query, or
the query returns/joins far too much). Counters accumulate since the last
`pg_stat_statements_reset()`; compare against a known window. More:
[14-observability/slow-queries.md](../14-observability/slow-queries.md).

### 3. Look at the plan (SQL)

`EXPLAIN` alone shows the plan without running it. `EXPLAIN ANALYZE`
**executes** the statement.

- **What it does:** runs the query for real and reports actual timings.
- **Why risky:** on `INSERT`/`UPDATE`/`DELETE`/DDL it performs the change. On a slow `SELECT` it consumes the same resources again.
- **Safer alternative:** plain `EXPLAIN` first; for writes, wrap in a transaction you roll back.
- **Precaution:** run it on a replica or a restored copy when possible; for writes use `BEGIN; EXPLAIN (ANALYZE, BUFFERS) ...; ROLLBACK;` (still takes the row locks while it runs); set `statement_timeout` in the session first.

```sql
SET statement_timeout = '60s';
EXPLAIN (ANALYZE, BUFFERS) SELECT * FROM events WHERE user_ref = 'q500';
```

What to look for (details in [05-performance/explain.md](../05-performance/explain.md)):

| In the plan | Meaning | Typical fix |
|---|---|---|
| `Seq Scan` on a large table with a selective `Filter:` and large `Rows Removed by Filter` | No usable index for that predicate | Add an index that serves this query (see [05-performance/indexes.md](../05-performance/indexes.md)) |
| Estimated `rows=` far from `actual rows=` | Stale or insufficient statistics | `ANALYZE table;` then re-plan |
| `Sort Method: external merge  Disk:` | Sort spilled to disk | Index that provides the order, or raise `work_mem` **for that session/role** |
| `Nested Loop` with huge `loops=` | Bad join estimate or missing index on the inner side | Statistics, join index |
| `Buffers: shared read=` large vs `hit` | Cold cache or too-big working set | Index, or memory |
| An expression in the predicate (`WHERE id + 0 = 500`, `lower(col) = ...`, a cast on the column) | Index on the bare column cannot be used | Rewrite the predicate or create an expression index |

Reproduced: `WHERE id + 0 = 500` produced a parallel `Seq Scan` over the
table, while `WHERE user_ref = 'q500'` used the index
(`Index Scan ... Execution Time: 0.135 ms`).

### 4. Statistics freshness and bloat (SQL)

```sql
SELECT relname, n_live_tup, n_dead_tup, n_mod_since_analyze,
       last_autovacuum, last_autoanalyze
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 10;
```

Large `n_mod_since_analyze` on a table the slow query reads means the
planner is working from old statistics: run `ANALYZE <table>;` (cheap,
non-blocking for reads/writes). Large `n_dead_tup` means vacuum is behind
(see [05-performance/vacuum.md](../05-performance/vacuum.md) and
[05-performance/analyze.md](../05-performance/analyze.md)).

### 5. Log slow statements

Settings (SQL; `log_min_duration_statement` is superuser-settable, reload
only, no restart). Value is illustrative; choose from your latency budget:

```sql
ALTER SYSTEM SET log_min_duration_statement = '500ms';
SELECT pg_reload_conf();
```

Revert with `ALTER SYSTEM RESET log_min_duration_statement; SELECT pg_reload_conf();`.
Logging every statement (`0`) on a busy system itself becomes a load and
disk-fill risk ([disk-full.md](disk-full.md)).

## Remediation (ordered, safest first)

| # | Action | Reversible | Risk |
|---|---|---|---|
| 1 | Stop the **source**: pause the report/batch/cron, disable the feature flag, roll back the deploy that introduced the query | Yes | Low |
| 2 | Add guard timeouts for the offending role: `ALTER ROLE report_user SET statement_timeout = '30s';` | Yes (`RESET`) | Low: new queries over the limit now fail |
| 3 | `ANALYZE <table>;` if statistics are stale | Yes | Low |
| 4 | Cancel the specific runaway query: `SELECT pg_cancel_backend(<PID>);` | n/a | Low: the statement's work is lost; the session stays |
| 5 | Add the index that serves the query: `CREATE INDEX CONCURRENTLY ...` | `DROP INDEX CONCURRENTLY` | Medium: see below |
| 6 | Terminate the session: `pg_terminate_backend(<PID>)` | No | See below |
| 7 | Rewrite the query / fix the ORM call (N+1, missing `LIMIT`, offset pagination on deep pages) | Via deploy | Needs code release |

### `pg_cancel_backend` vs `pg_terminate_backend`

- **What they do:** `pg_cancel_backend(pid)` sends a cancel to the running query (session survives, transaction goes to aborted state if one is open). `pg_terminate_backend(pid)` closes the session and rolls back its transaction.
- **Why risky:** work is lost; a cancelled or terminated `UPDATE`/`DELETE`/`INSERT` is rolled back, which can take as long as it ran; the app must handle the error.
- **Safer alternative:** cancel before terminate; set `statement_timeout` so this happens automatically.
- **Precaution:** confirm pid, user, application, and query text first; never target replication or autovacuum backends; if the query is a `CREATE INDEX CONCURRENTLY`, cancelling leaves an `INVALID` index ([failed-migration.md](failed-migration.md)).

### Adding an index during an incident

Plain `CREATE INDEX` blocks writes to the table for the whole build.
`CREATE INDEX CONCURRENTLY` does not block writes but is slower, uses extra
I/O and cannot run inside a transaction block (error:
`CREATE INDEX CONCURRENTLY cannot run inside a transaction block`). Every
index adds storage and slows `INSERT`/`UPDATE` on that table: add only the
index the slow query's plan justifies, and verify with `EXPLAIN` after.
If it fails it leaves an `INVALID` index; see
[failed-migration.md](failed-migration.md#case-c-invalid-indexes-after-create-index-concurrently).

```sql
CREATE INDEX CONCURRENTLY ix_events_user_ref ON events (user_ref);
```

### Memory settings

Do not raise global `work_mem` during an incident: it is allocated **per
sort/hash node per connection**, so a global increase multiplies by
concurrency and can cause out-of-memory kills. Raise it for one role or
session (`ALTER ROLE report_user SET work_mem = '256MB';`, value
illustrative) and watch memory.

## Verification

```sql
EXPLAIN (ANALYZE, BUFFERS) <the same query>;   -- plan changed? actual time down?
```

- [ ] The query's `mean_exec_time` in `pg_stat_statements` drops on subsequent calls (reset or compare windows).
- [ ] The active-session triage query shows no long runners and no pile-up.
- [ ] Application p95/p99 latency and error rate back to baseline.
- [ ] CPU, I/O, and connection count normal.

## Prevention

- Enable `pg_stat_statements` and review top queries by `total_exec_time` regularly ([14-observability/slow-queries.md](../14-observability/slow-queries.md)).
- Set `statement_timeout` and `idle_in_transaction_session_timeout` per role, with longer values for batch roles.
- Run `EXPLAIN` on new queries against production-sized data before release; keyset pagination instead of deep `OFFSET`.
- Keep autovacuum healthy; alert on `n_dead_tup` growth and old transactions.
- Review new indexes with the tradeoff stated: which query, read gain versus write/storage cost ([05-performance/indexes.md](../05-performance/indexes.md)).
- Checklist: [05-performance/performance-checklist.md](../05-performance/performance-checklist.md); rewrites: [05-performance/query-optimization.md](../05-performance/query-optimization.md).

## Escalation / When to stop

- Plan is reasonable, statistics fresh, query still slow: the data volume or hardware has outgrown the design. Escalate to a DBA/architect (partitioning, replicas, resource increase); do not keep adding indexes.
- Slowdown is global (every query), CPU/I/O saturated by non-database processes, or disk latency is high: platform/infra issue.
- Wait events show `LWLock`/`BufferPin` storms or the server is swapping: reduce concurrency first, then escalate.
