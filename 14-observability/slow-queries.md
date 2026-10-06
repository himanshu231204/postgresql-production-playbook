# Finding Slow Queries

PostgreSQL 16 (column names below are PG13+). Once a query is found, use
[../05-performance/explain.md](../05-performance/explain.md) to see why it
is slow and [../05-performance/indexes.md](../05-performance/indexes.md) to
decide on an index. Incident procedure:
[../15-production-runbooks/slow-query.md](../15-production-runbooks/slow-query.md).

## What it is

Three complementary sources: `pg_stat_activity` (what is slow *now*),
`pg_stat_statements` (cumulative cost per normalized query), and the
server log (`log_min_duration_statement`, `auto_explain`).

## Why it matters

Per-query cost is only visible in aggregate: a 5 ms query executed
10,000 times per minute can cost more than one 5 s report. Total time,
call count, and mean time answer different questions.

## pg_stat_statements

Setup (requires a restart; changing `shared_preload_libraries` is not
reloadable):

```ini
# postgresql.conf
shared_preload_libraries = 'pg_stat_statements'   # append to any existing list
```

Restart PostgreSQL, then per database where you want to query it:

```sql
CREATE EXTENSION pg_stat_statements;
```

Defaults on PG16: `pg_stat_statements.max = 5000` statements,
`pg_stat_statements.track = top`, and `compute_query_id = auto` (enabled
automatically by the extension). Set `track_io_timing = on` (default
`off`) to populate the `blk_read_time`/`blk_write_time` columns; it adds
timing overhead, so measure on your hardware
(`pg_test_timing`).

Queries are normalized: constants become `$1`, `$2`, so
`WHERE id = 5` and `WHERE id = 9` aggregate to one row.

Top queries by total time (where the server spends its time):

```sql
SELECT queryid, calls,
       round(total_exec_time::numeric, 1) AS total_ms,
       round(mean_exec_time::numeric, 2)  AS mean_ms,
       round(stddev_exec_time::numeric, 2) AS stddev_ms,
       rows, shared_blks_hit, shared_blks_read,
       left(query, 60) AS query
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 10;
```

Slowest on average (candidates for per-call tuning):

```sql
SELECT queryid, calls,
       round(mean_exec_time::numeric, 2) AS mean_ms,
       round(max_exec_time::numeric, 2)  AS max_ms,
       left(query, 60) AS query
FROM pg_stat_statements
WHERE calls >= 1      -- raise the floor to ignore one-off statements
ORDER BY mean_exec_time DESC
LIMIT 10;
```

Spilling to disk (candidate for `work_mem` or query changes):

```sql
SELECT queryid, calls, temp_blks_written, left(query, 60) AS query
FROM pg_stat_statements
WHERE temp_blks_written > 0
ORDER BY temp_blks_written DESC
LIMIT 10;
```

Most disk reads (cache-unfriendly queries):

```sql
SELECT queryid, shared_blks_hit, shared_blks_read,
       round(100.0 * shared_blks_hit / NULLIF(shared_blks_hit + shared_blks_read, 0), 2) AS hit_pct,
       left(query, 60) AS query
FROM pg_stat_statements
ORDER BY shared_blks_read DESC
LIMIT 10;
```

Version notes: before PG13 the columns were `total_time`/`mean_time`;
PG13+ split planning and execution (`total_exec_time`, `mean_exec_time`,
`total_plan_time` when `pg_stat_statements.track_planning` is on).

Statistics are cumulative since the last reset. Compare two snapshots
(for example, dump to a table on a schedule) rather than reading absolute
totals after months of uptime. `pg_stat_statements_info` (PG14+) shows the number
of times entries were evicted (`dealloc`) and the last reset time.

**`pg_stat_statements_reset()` (destructive to diagnostics):** discards all
collected statement statistics (with no arguments, for every user,
database, and query). It does not change data, but you lose the
history, and monitoring that computes deltas will see a counter drop.
Precaution: save the top-N output first, run it only from a role you
intend to have this privilege (it is superuser-only by default), and
announce it. In PG16 it returns `void` (newer versions differ), and
accepts `(userid, dbid, queryid)` to reset a narrower scope.

## log_min_duration_statement

Logs every statement running at least the given time, after completion:

```sql
ALTER SYSTEM SET log_min_duration_statement = '500ms';   -- example value
SELECT pg_reload_conf();
```

| Value | Effect |
|---|---|
| `-1` (default) | Disabled |
| `0` | Log every statement with its duration (very high volume) |
| `250ms`, `1s`, ... | Log statements at least that slow |

Choose the value from your latency distribution (for example from the
`mean_exec_time`/`max_exec_time` of your hot queries); there is no
universal "slow". Logging parameter values and query text can expose
sensitive data; restrict log access (see [../06-security/](../06-security/README.md)).
Related: `log_lock_waits` (see [pg-locks.md](pg-locks.md)),
`log_temp_files`, `log_autovacuum_min_duration`.

`log_statement_sample_rate` / `log_min_duration_sample` exist to sample
instead of logging everything on busy systems (PG13+).

## auto_explain

Logs the execution plan of slow statements automatically, so the plan
from the real production data is captured when it happened:

```ini
# postgresql.conf (or session_preload_libraries); restart required for shared_preload_libraries
shared_preload_libraries = 'pg_stat_statements,auto_explain'
auto_explain.log_min_duration = '1s'    # example; -1 (default) disables
```

`auto_explain.log_analyze = on` gives real row counts and timings but
adds timing overhead to every statement, not just slow ones; leave it off
until needed. For one session (superuser): `LOAD 'auto_explain';` then
`SET auto_explain.log_min_duration = '1ms';`. This was verified: the plan
appears in the server log beside the `duration:` line.

## Per-table and per-index usage

Cumulative counters since the last stats reset
(`pg_stat_database.stats_reset`):

```sql
SELECT relname, n_live_tup, n_dead_tup,
       round(100.0 * n_dead_tup / NULLIF(n_live_tup + n_dead_tup, 0), 1) AS dead_pct,
       seq_scan, seq_tup_read, idx_scan,
       n_tup_ins, n_tup_upd, n_tup_del, n_tup_hot_upd,
       last_autovacuum, last_autoanalyze
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 20;
```

A high `seq_tup_read` with low `idx_scan` on a large table points to a
missing or unusable index; confirm with `EXPLAIN`. A table with many dead
tuples and no recent `last_autovacuum` points to
[../05-performance/vacuum.md](../05-performance/vacuum.md).

Indexes never scanned since the reset (candidates, not proof, for removal):

```sql
SELECT s.schemaname, s.relname, s.indexrelname, s.idx_scan,
       pg_size_pretty(pg_relation_size(s.indexrelid)) AS index_size
FROM pg_stat_user_indexes s
JOIN pg_index i ON i.indexrelid = s.indexrelid
WHERE s.idx_scan = 0 AND NOT i.indisunique AND NOT i.indisprimary
ORDER BY pg_relation_size(s.indexrelid) DESC;
```

Before dropping: confirm the stats window covers a full business cycle
(month-end jobs), check replicas (their scans count separately), and drop
with `DROP INDEX CONCURRENTLY` (still destructive: it removes the index;
recreating on a large table takes time). Unique/primary indexes enforce
constraints even when never scanned, hence the filter. See
[../05-performance/indexes.md](../05-performance/indexes.md).

## Common mistakes

- Reading `pg_stat_statements` totals without knowing when they were last reset.
- Optimizing the highest `mean_exec_time` instead of the highest `total_exec_time` (or vice versa) without choosing by the actual symptom.
- Setting `log_min_duration_statement = 0` in production and filling the disk.
- Dropping "unused" indexes from a primary whose reads happen on a replica.
- Expecting `CREATE EXTENSION` alone to work: without the `shared_preload_libraries` entry and restart, queries fail with "must be loaded via shared_preload_libraries".

## AI/agentic use case

Agent tool-call and retrieval queries are often generated by an ORM or
templates and run at high call counts; `pg_stat_statements` by
`total_exec_time` and `calls` shows which agent code paths dominate load.
Tag sessions with `application_name` per agent service.

## Quick revision

- `shared_preload_libraries` + restart + `CREATE EXTENSION`.
- Sort by `total_exec_time` for load, `mean_exec_time` for per-call slowness.
- Log slow statements with `log_min_duration_statement`; capture plans with `auto_explain`.
- Counters are cumulative; compare snapshots.
