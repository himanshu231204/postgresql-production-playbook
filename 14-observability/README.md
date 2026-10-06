# Observability

## What it is

The built-in PostgreSQL views, functions, and logs that answer "what is the
database doing right now, and what has it been doing?" — plus the
health-check and diagnostic scripts in this repo that wrap them.

All queries in this section target **PostgreSQL 16** and were executed
against a PostgreSQL 16 server. Version differences are called out inline.

## Why it matters

During an incident the first question is always which session, which query,
which lock, which table. These views answer it without installing anything
beyond `pg_stat_statements`. Metrics and alerts (see
[monitoring.md](monitoring.md)) tell you *that* something is wrong; these
queries tell you *what*.

## In this section

| Page | Covers |
|---|---|
| [monitoring.md](monitoring.md) | What to watch and alert on, `pg_stat_database`, connection/replication/XID-age signals, exporters |
| [pg-stat-activity.md](pg-stat-activity.md) | Live sessions, wait events, idle-in-transaction, `pg_cancel_backend` vs `pg_terminate_backend` |
| [pg-locks.md](pg-locks.md) | `pg_locks`, `pg_blocking_pids()`, finding the root blocker |
| [slow-queries.md](slow-queries.md) | `pg_stat_statements`, `log_min_duration_statement`, `auto_explain`, table/index usage stats |
| [database-size.md](database-size.md) | Database, table, and index sizes; growth tracking |
| [health-checks.md](health-checks.md) | Liveness vs readiness, `pg_isready` exit codes, the health-check script |

Scripts: [scripts/health-check/](../scripts/health-check/README.md) and
[scripts/diagnostics/](../scripts/diagnostics/README.md).

## Permissions

Most views show full detail only for your own sessions unless you are a
superuser or a member of `pg_read_all_stats` (query text and activity of
other roles) — the built-in `pg_monitor` role includes it. Grant
`pg_monitor` to a dedicated monitoring role instead of using a superuser;
see [../06-security/roles.md](../06-security/roles.md).
Cancelling or terminating other roles' sessions needs superuser,
membership in the target's role, or `pg_signal_backend`.

## Incident entry points

- Slow queries: [../15-production-runbooks/slow-query.md](../15-production-runbooks/slow-query.md)
- Blocked queries: [../15-production-runbooks/lock-contention.md](../15-production-runbooks/lock-contention.md)
- Connection limit hit: [../15-production-runbooks/connection-exhaustion.md](../15-production-runbooks/connection-exhaustion.md)
- Disk filling: [../15-production-runbooks/disk-full.md](../15-production-runbooks/disk-full.md)
- Server down: [../15-production-runbooks/database-is-down.md](../15-production-runbooks/database-is-down.md)

## Quick revision

- `pg_stat_activity` = who is doing what now; `pg_locks` + `pg_blocking_pids()` = who blocks whom.
- `pg_stat_statements` = which normalized queries cost the most over time.
- `pg_stat_database` / `pg_stat_user_tables` = cumulative counters; compare deltas, not absolutes.
- Sizes: `pg_total_relation_size` includes indexes and TOAST.
- Health checks: `pg_isready` for liveness, a real query for readiness.
