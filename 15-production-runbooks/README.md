# Production Runbooks

Incident runbooks for PostgreSQL 16. Each page is built to be opened
mid-incident: symptoms, a 2-minute triage, exact diagnosis commands,
remediation ordered safest-first, verification, prevention, and a "when to
stop and escalate" gate.

## Pick a runbook

| Symptom you are seeing | Runbook |
|---|---|
| `connection refused`, `no response`, `could not connect`, server process missing, crash loop | [database-is-down.md](database-is-down.md) |
| `sorry, too many clients already`, `remaining connection slots are reserved...`, pool timeouts | [connection-exhaustion.md](connection-exhaustion.md) |
| API latency up, CPU high, one query or endpoint slow, queries pile up | [slow-query.md](slow-query.md) |
| Queries hang with no error, `canceling statement due to lock timeout`, `deadlock detected` | [lock-contention.md](lock-contention.md) |
| `No space left on device`, `PANIC: could not write to file`, data volume at 100% | [disk-full.md](disk-full.md) |
| Deploy stuck or failed during a schema migration, `INVALID` index, app/schema mismatch | [failed-migration.md](failed-migration.md) |
| Data loss, corruption, bad deploy that wrote wrong data, need to recover a database | [restore-database.md](restore-database.md) |

Not sure which one? Start with the triage table below, then follow the
runbook it points to.

## First 2 minutes: which runbook?

Run from a shell with network access to the database. These are Unix shell
commands (macOS/Linux); on Windows use PowerShell
`Test-NetConnection -ComputerName HOST -Port 5432` for the port check and
`pg_isready.exe` from the PostgreSQL `bin` directory.

```bash
pg_isready -h HOST -p 5432
```

| `pg_isready` exit code | Meaning | Go to |
|---|---|---|
| `0` | Server accepting connections | Continue below |
| `1` | Server running but rejecting connections (startup, crash recovery, or shutdown in progress) | [database-is-down.md](database-is-down.md) |
| `2` | No response (server down, wrong host/port, firewall) | [database-is-down.md](database-is-down.md) |
| `3` | No attempt made (invalid parameters to `pg_isready`) | Fix the command, rerun |

If the server accepts connections, connect (`psql "host=HOST dbname=postgres user=ADMIN_USER"`)
and run this one query (SQL):

```sql
SELECT
  count(*) FILTER (WHERE state = 'active')                                   AS active,
  count(*) FILTER (WHERE state = 'idle in transaction')                      AS idle_in_txn,
  count(*) FILTER (WHERE wait_event_type = 'Lock')                           AS waiting_on_lock,
  count(*)                                                                   AS total_clients,
  current_setting('max_connections')::int                                    AS max_connections,
  max(now() - xact_start) FILTER (WHERE xact_start IS NOT NULL)              AS oldest_xact
FROM pg_stat_activity
WHERE backend_type = 'client backend';
```

| Reading | Likely incident |
|---|---|
| `total_clients` near `max_connections` | [connection-exhaustion.md](connection-exhaustion.md) |
| `waiting_on_lock` high | [lock-contention.md](lock-contention.md) |
| `active` high, nothing waiting on locks, CPU high | [slow-query.md](slow-query.md) |
| Cannot even connect, or errors mention disk / WAL / `No space left` | [disk-full.md](disk-full.md) |
| Started within minutes of a deploy that ran a migration | [failed-migration.md](failed-migration.md) |

## General incident-handling checklist

Applies to every runbook. Order matters: stabilize first, root-cause later.

### 1. Declare and communicate (first 5 minutes)

- [ ] Name one **incident lead** (decides) and one **scribe** (records). Do not let the person typing commands also keep the timeline.
- [ ] Post in the incident channel: what is impacted, since when (UTC), who leads. Update at a fixed cadence (every 15-30 minutes) even if the update is "no change."
- [ ] Tell the application owners what to expect (errors, retries, brief connection drops) **before** any step that terminates sessions or restarts the server.

### 2. Stabilize before root-causing

- [ ] Stop the bleeding first: shed load, pause batch jobs and cron, stop the deploy, scale the app tier down, enable maintenance mode. A smaller, steady failure is easier to diagnose than a growing one.
- [ ] Prefer **reversible** actions first (cancel a query, set a timeout, pause a job) over **irreversible** ones (terminate sessions, drop a slot, restore over data).
- [ ] Capture evidence **before** it disappears: save the output of the diagnosis queries (`pg_stat_activity`, `pg_locks`, `pg_replication_slots`) and the relevant log lines. Killing sessions and restarting the server destroys this state.
- [ ] Change **one thing at a time** and record the time and the effect.

### 3. Record the timeline

Keep a running, timestamped (UTC) log:

| Time (UTC) | Who | Observation or action | Result |
|---|---|---|---|
| 14:02 | alice | Alerts: API p95 up, connection count 98/100 | |
| 14:05 | bob | Ran `pg_stat_activity` triage, 70 sessions `idle in transaction` from `batch-job` | |

Include: first alert, first customer report, every command run against
production, every config change, every decision and who made it.

### 4. Destructive-action gate

Before running any of these, the lead says "go" and the scribe records it.
Every runbook flags them with the same four points: what it does, why it is
risky, the safer alternative, the precaution (see
[AGENTS.md](../AGENTS.md#18-production-safety-in-content)).

| Command | Risk | Safer alternative first |
|---|---|---|
| `pg_terminate_backend()` | Rolls back the session's transaction; client sees a dropped connection | `pg_cancel_backend()` (cancels the running query, keeps the session) |
| `pg_drop_replication_slot()` | Breaks the consumer (replica or CDC) permanently if it still needs the WAL | Fix or resume the consumer; set `max_slot_wal_keep_size` |
| `DROP INDEX`, `DROP TABLE`, `DROP DATABASE` | Irreversible without a restore | Rename, or take a backup first |
| `DELETE` / `TRUNCATE` at scale | Long locks, WAL/bloat explosion, or total data loss | Batched deletes; `pg_dump` the rows first |
| `VACUUM FULL` | `ACCESS EXCLUSIVE` lock for the full duration; needs free space equal to the table | Plain `VACUUM`; `pg_repack` for online compaction |
| Deleting files in `pg_wal/` | Corrupts the cluster (unrecoverable) | Never. Fix the cause (slot, archiving, disk) |
| `kill -9` on the postmaster | Forces crash recovery; can lose in-flight transactions' work | `pg_ctl stop -m fast` |
| `pg_resetwal` | Can produce an inconsistent, silently corrupt database | Restore from backup/PITR. Last resort, with a copy of the data directory |
| Restoring over a live database | Overwrites current data | Restore to a **new** instance, verify, then cut over |

### 5. Post-incident (within 2 business days)

- [ ] Write a blameless review: impact, timeline, root cause, what worked, what did not, what was lucky.
- [ ] Separate **trigger** (what happened) from **contributing conditions** (why it was able to hurt: no timeout, no alert, no pooler).
- [ ] File follow-up tasks with owners and dates. Each runbook's **Prevention** section is the starting list.
- [ ] Update the runbook that was used. If you had to improvise a command, add it here.
- [ ] Verify alerts fire at an actionable threshold (see [14-observability/monitoring.md](../14-observability/monitoring.md)).

## Conventions used in these runbooks

- Command types are labeled: `bash` blocks are Unix shell (macOS/Linux), `powershell` blocks are Windows PowerShell, `sql` blocks run inside any SQL session, and psql meta-commands (`\x`, `\conninfo`) are called out as psql client commands.
- `HOST`, `ADMIN_USER`, `APP_USER`, `DATABASE`, and `<PID>` are placeholders. Never paste real passwords into tickets; use `PGPASSWORD` from a secrets manager or a `~/.pgpass` file.
- Queries that need elevated privileges say so (`pg_monitor` role or superuser).
- Version baseline is PostgreSQL 16. Version differences are noted where they matter.
- On managed services (RDS, Cloud SQL, Azure Database for PostgreSQL), you have no shell on the host and no superuser. Host-level steps (data directory, `pg_ctl`, `journalctl`) become provider console actions; the SQL diagnosis still applies. Provider specifics: [13-cloud-production/managed-postgresql.md](../13-cloud-production/managed-postgresql.md).

## Related

- Diagnostic queries: [14-observability/pg-stat-activity.md](../14-observability/pg-stat-activity.md), [14-observability/pg-locks.md](../14-observability/pg-locks.md), [14-observability/slow-queries.md](../14-observability/slow-queries.md), [14-observability/database-size.md](../14-observability/database-size.md), [14-observability/health-checks.md](../14-observability/health-checks.md)
- Prevention: [05-performance/connection-pooling.md](../05-performance/connection-pooling.md), [05-performance/performance-checklist.md](../05-performance/performance-checklist.md), [04-transactions/locking.md](../04-transactions/locking.md)
- Recovery: [07-backups-recovery/disaster-recovery.md](../07-backups-recovery/disaster-recovery.md), [07-backups-recovery/point-in-time-recovery.md](../07-backups-recovery/point-in-time-recovery.md)
