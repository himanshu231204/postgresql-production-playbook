# Monitoring PostgreSQL

PostgreSQL 16; every query executed against a PostgreSQL 16 server
(replication queries against a primary plus streaming standby). Pages
for drilling down: [pg-stat-activity.md](pg-stat-activity.md),
[pg-locks.md](pg-locks.md), [slow-queries.md](slow-queries.md),
[database-size.md](database-size.md).

## What it is

Continuously collecting the cumulative counters and point-in-time state
PostgreSQL exposes (`pg_stat_*` views, `pg_settings`, size functions) and
alerting on symptoms.

## Why it matters

Counters in `pg_stat_*` are cumulative since startup or the last stats
reset: a single reading says little, the **rate of change** says a lot.
Monitoring is what turns them into rates and history.

## What to monitor and why

| Signal | Source | Failure it predicts |
|---|---|---|
| Server reachable, accepts connections | `pg_isready`, a `SELECT 1` ([health-checks.md](health-checks.md)) | Outage |
| Connections used vs `max_connections` | `pg_stat_activity` | "too many clients" errors; see [../15-production-runbooks/connection-exhaustion.md](../15-production-runbooks/connection-exhaustion.md) |
| Sessions `idle in transaction`, oldest `xact_start` | `pg_stat_activity` | Lock pile-ups, blocked VACUUM |
| Sessions waiting on `Lock` | `pg_stat_activity`, `pg_blocking_pids()` | Request latency, timeouts |
| Query latency / throughput by statement | `pg_stat_statements` | Regressions, new hot queries |
| Deadlocks, rollbacks, temp files | `pg_stat_database` | App bugs, undersized `work_mem` |
| Cache hit ratio trend | `pg_stat_database` | Working set outgrew memory (trend, not a fixed target) |
| Dead tuples, last autovacuum | `pg_stat_user_tables` | Bloat; see [../05-performance/vacuum.md](../05-performance/vacuum.md) |
| Transaction ID age | `pg_database` | Wraparound protection forcing aggressive vacuum or, in the worst case, a shutdown to protect data |
| Replication lag, slot retained WAL | `pg_stat_replication`, `pg_replication_slots` | Stale replicas; disk filling from WAL |
| Database / table / disk growth | size functions + host metrics | [../15-production-runbooks/disk-full.md](../15-production-runbooks/disk-full.md) |
| Backup success and age | backup tooling | Unrecoverable data; see [../07-backups-recovery/backup-strategy.md](../07-backups-recovery/backup-strategy.md) |
| Host: CPU, memory, disk I/O, free space | OS / cloud metrics | Everything above, at the hardware level |

## Queries (SQL)

### Database-level counters

```sql
SELECT datname, numbackends, xact_commit, xact_rollback,
       blks_read, blks_hit,
       round(100.0 * blks_hit / NULLIF(blks_hit + blks_read, 0), 2) AS cache_hit_pct,
       deadlocks, conflicts, temp_files,
       pg_size_pretty(temp_bytes) AS temp_bytes, stats_reset
FROM pg_stat_database
WHERE datname = current_database();
```

- `cache_hit_pct` counts hits in PostgreSQL's shared buffers only; reads
  served by the OS page cache still count as `blks_read`. A low or
  falling value is a prompt to look at which queries read most
  (`shared_blks_read` in `pg_stat_statements`), not a verdict.
  Large sequential scans (reports, backups) lower it legitimately.
- `deadlocks`, `temp_files`, `xact_rollback` should be graphed as rates.
  A sudden change in rate is the signal.
- `stats_reset` tells you the window the counters cover. Statistics are
  lost after a crash or immediate shutdown; they survive a clean restart.

### Connection headroom

```sql
SELECT count(*) AS client_backends,
       current_setting('max_connections')::int AS max_connections,
       current_setting('superuser_reserved_connections')::int AS superuser_reserved
FROM pg_stat_activity
WHERE backend_type = 'client backend';
```

Alert on proximity to `max_connections` relative to how fast your
application can grow connections; consider a pooler
([../05-performance/connection-pooling.md](../05-performance/connection-pooling.md)).
`superuser_reserved_connections` slots are unavailable to ordinary roles.

### Transaction ID age (wraparound)

```sql
SELECT datname,
       age(datfrozenxid)      AS xid_age,
       mxid_age(datminmxid)   AS mxid_age,
       current_setting('autovacuum_freeze_max_age') AS autovacuum_freeze_max_age
FROM pg_database
ORDER BY age(datfrozenxid) DESC;
```

Per table (which table is holding the oldest XID back):

```sql
SELECT c.oid::regclass AS "table", age(c.relfrozenxid) AS xid_age
FROM pg_class c
WHERE c.relkind IN ('r', 'm')
  AND c.relnamespace NOT IN (SELECT oid FROM pg_namespace
                             WHERE nspname IN ('pg_catalog', 'information_schema'))
ORDER BY age(c.relfrozenxid) DESC
LIMIT 10;
```

Autovacuum starts anti-wraparound vacuums as `xid_age` approaches
`autovacuum_freeze_max_age` (default 200 million). Alert on a database
whose `xid_age` keeps growing past that setting, which means vacuum is
not keeping up (long transactions, abandoned replication slots, or
prepared transactions are the usual causes). Rising age is a trend to
alert on; the absolute number depends on your configuration.

### Replication lag

On the **primary**:

```sql
SELECT application_name, client_addr, state, sync_state,
       pg_wal_lsn_diff(pg_current_wal_lsn(), sent_lsn)   AS sent_lag_bytes,
       pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS replay_lag_bytes,
       write_lag, flush_lag, replay_lag
FROM pg_stat_replication;
```

Verified output on a local streaming standby:

```text
 application_name | client_addr |   state   | sync_state | sent_lag_bytes | replay_lag_bytes | write_lag | flush_lag | replay_lag
------------------+-------------+-----------+------------+----------------+------------------+-----------------+...
 walreceiver      | 127.0.0.1   | streaming | async      |              0 |                0 | 00:00:00.073499 | ...
```

A standby that is not connected has **no row** — alert on the expected
number of standbys, not only on lag values. `write_lag`/`flush_lag`/
`replay_lag` are time measurements and are NULL when there has been no
recent WAL activity.

Replication slots can force the primary to retain WAL while a consumer is
away:

```sql
SELECT slot_name, slot_type, active, wal_status,
       pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS retained_wal
FROM pg_replication_slots;
```

An inactive slot with growing `retained_wal` fills the WAL disk.
Dropping a slot (`pg_drop_replication_slot`) is destructive for its
consumer, which must be rebuilt or resynchronized; confirm it is truly
abandoned first.

On a **standby**:

```sql
SELECT pg_is_in_recovery() AS in_recovery,
       pg_last_wal_receive_lsn() AS received,
       pg_last_wal_replay_lsn()  AS replayed,
       now() - pg_last_xact_replay_timestamp() AS replay_delay;

SELECT status, receive_start_lsn, flushed_lsn, latest_end_lsn,
       last_msg_receipt_time, sender_host, sender_port
FROM pg_stat_wal_receiver;
```

`pg_stat_wal_receiver` returns no row if the WAL receiver is not running.
`replay_delay` measures time since the last replayed commit, so on a
primary with **no write traffic** it grows even though the standby is
fully caught up; compare `received` and `replayed` LSNs as well.

## What to alert on

Alert on symptoms users or operators feel, and tune each alert from your
own baseline; this repo does not prescribe universal numbers.

| Alert | Page or ticket |
|---|---|
| Health check failing (not accepting connections / cannot run a query) | Page |
| Connection count approaching `max_connections`, or "too many clients" errors in logs | Page |
| Standby missing or lag growing without recovery | Page for HA-critical replicas |
| Disk free space falling toward zero, or WAL retained by an inactive slot growing | Page (hard outage if it hits zero) |
| Oldest transaction / idle-in-transaction age growing | Ticket, page if it blocks others |
| Lock waits piling up (sessions with `wait_event_type = 'Lock'`) | Page when user-visible |
| Deadlocks rate rising | Ticket |
| XID age rising despite autovacuum running | Ticket early, page when approaching the freeze limit |
| Latest successful backup older than your RPO | Page |
| p95/p99 latency of key queries regressing | Ticket / page by SLO |

## Exporters and dashboards

`postgres_exporter` (Prometheus community project) exposes many of the
above views to Prometheus; its metric names, flags, and custom-query
format differ by version, so take them from the project's README for the
version you deploy. Managed providers expose their own metrics under
different names; see [../13-cloud-production/](../13-cloud-production/README.md).
Create a dedicated monitoring role with `GRANT pg_monitor TO monitoring_user;`
rather than a superuser; credentials come from a secrets manager or
environment variable, never from the exporter's config committed to Git
([../06-security/passwords-and-secrets.md](../06-security/passwords-and-secrets.md)).

## Common mistakes

- Alerting on a cumulative counter's absolute value instead of its rate.
- Treating cache hit ratio as a pass/fail number.
- Monitoring only the primary; a dead standby or stuck slot goes unnoticed.
- Running monitoring as a superuser, or from a role limited to its own sessions so queries return NULLs.
- Polling heavy queries (table sizes of thousands of relations, bloat estimates) every few seconds.

## Quick revision

- Graph rates of counters; alert on symptoms.
- Watch: connections, idle-in-transaction age, lock waits, replication, XID age, disk, backups.
- `pg_monitor` for the monitoring role; never a superuser.
- Exporters collect these; check their docs for names.
