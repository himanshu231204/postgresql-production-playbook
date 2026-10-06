# Runbook: Lock Contention

Applies to PostgreSQL 16. Background on lock modes:
[04-transactions/locking.md](../04-transactions/locking.md); deadlock
theory: [04-transactions/deadlocks.md](../04-transactions/deadlocks.md).

## Symptoms

- Queries hang with no error; connection count and latency climb.
- Many sessions with `wait_event_type = 'Lock'` in `pg_stat_activity`.
- `ERROR: canceling statement due to lock timeout` (a `lock_timeout` fired).
- `ERROR: deadlock detected` (SQLSTATE `40P01`).
- Right after a migration started: *all* queries on one table stall, even plain `SELECT`s.

## Triage (first 2 minutes)

SQL: who is waiting, and on whom.

```sql
SELECT a.pid, a.usename, a.application_name, a.state,
       a.wait_event_type, a.wait_event,
       pg_blocking_pids(a.pid)  AS blocked_by,
       now() - a.query_start    AS waiting_for,
       left(a.query, 80)        AS query
FROM pg_stat_activity a
WHERE cardinality(pg_blocking_pids(a.pid)) > 0
ORDER BY a.query_start;
```

Now find the **root blockers**: sessions that block others but are not
blocked themselves. Killing a middle-of-the-chain session does not help.

```sql
SELECT b.pid                       AS root_blocker_pid,
       b.usename, b.application_name, b.state,
       now() - b.xact_start        AS xact_age,
       now() - b.state_change      AS in_state_for,
       left(b.query, 80)           AS last_query,
       (SELECT count(*) FROM pg_stat_activity w
         WHERE b.pid = ANY (pg_blocking_pids(w.pid))) AS directly_blocking
FROM pg_stat_activity b
WHERE b.pid IN (SELECT unnest(pg_blocking_pids(pid)) FROM pg_stat_activity)
  AND cardinality(pg_blocking_pids(b.pid)) = 0;
```

Reproduced result: a session in `idle in transaction` that ran an `UPDATE`
and never committed was the root, with two writers queued behind it (the
second writer waited on the first via a `tuple` lock, one hop removed).
`pg_blocking_pids()` returns direct blockers only; the root query above
collapses the chain.

| Root blocker `state` | Meaning | Next |
|---|---|---|
| `idle in transaction` | App began a transaction, ran something, and stopped (bug, crashed client, long external call) | [Remediation 2](#remediation-ordered-safest-first); fix app |
| `active` on a long `UPDATE`/`DELETE`/DDL/batch | A legitimately long statement holds locks | Wait if short; cancel if it is a runaway |
| `active`, query is `ALTER TABLE` / `CREATE INDEX` (non-concurrent) / `VACUUM FULL` / `LOCK TABLE` | **DDL lock queue**, below | [DDL queue](#the-ddl-lock-queue) |
| `idle in transaction (aborted)` | Transaction failed and the client never rolled back | Terminate; fix app error handling |
| Prepared transaction (no pid; shown in `pg_prepared_xacts`) | Abandoned two-phase commit | [Prepared transactions](#abandoned-prepared-transactions) |

## Diagnosis

### Lock details (SQL)

```sql
SELECT l.pid, l.locktype, l.mode, l.granted,
       l.relation::regclass AS relation
FROM pg_locks l
WHERE NOT l.granted
   OR l.relation IN (SELECT relation FROM pg_locks WHERE NOT granted AND relation IS NOT NULL)
ORDER BY l.relation, l.granted DESC, l.pid;
```

More queries and column meanings:
[14-observability/pg-locks.md](../14-observability/pg-locks.md),
[14-observability/pg-stat-activity.md](../14-observability/pg-stat-activity.md).

### The DDL lock queue

A schema change that needs `ACCESS EXCLUSIVE` (most `ALTER TABLE` forms)
waits behind any open transaction that touched the table, even one that
only ran a `SELECT`. While it waits, **every later query on that table,
including plain reads, queues behind the DDL**. Reproduced:

| pid | application | state | blocked_by | lock |
|---|---|---|---|---|
| A | report-tx | idle in transaction | none | `AccessShareLock` granted |
| B | migration | active (`ALTER TABLE orders ADD COLUMN ...`) | A | `AccessExclusiveLock` **not granted** |
| C | api-worker | active (`SELECT ... FROM orders`) | B | `AccessShareLock` **not granted** |

The fix is to resolve the root (A) or cancel the DDL (B). Cancelling B
instantly releases C. Migration-side prevention (set `lock_timeout` in
migrations, retry): [failed-migration.md](failed-migration.md) and
[09-alembic/production-migrations.md](../09-alembic/production-migrations.md).

### Deadlocks

PostgreSQL resolves deadlocks itself after `deadlock_timeout` (default 1s)
by aborting one participant. The client sees:

```text
ERROR:  deadlock detected
DETAIL:  Process 2337 waits for ShareLock on transaction 747; blocked by process 2338.
Process 2338 waits for ShareLock on transaction 748; blocked by process 2337.
HINT:  See server log for query details.
CONTEXT:  while updating tuple (0,2) in relation "orders"
```

The **server log** adds the statement each process was running (this is
what you need):

```text
ERROR:  deadlock detected
DETAIL:  Process 2337 waits for ShareLock on transaction 747; blocked by process 2338.
	Process 2338 waits for ShareLock on transaction 748; blocked by process 2337.
	Process 2337: update orders set status='b' where id=2;
	Process 2338: update orders set status='a' where id=3;
```

Find log lines: `grep -n "deadlock detected" -A8 <logfile>` (Unix shell;
log location in [database-is-down.md](database-is-down.md#step-1-read-the-log-it-names-the-cause)),
and count with `SELECT datname, deadlocks FROM pg_stat_database;`.
No manual kill is needed; the work is to find the two code paths that lock
rows in opposite order, and make the application retry `40P01`. Enable
`log_lock_waits = on` to log any lock wait longer than `deadlock_timeout`,
with the blocker's pid.

### Abandoned prepared transactions

```sql
SELECT gid, prepared, owner, database, now() - prepared AS age
FROM pg_prepared_xacts;
```

A row here holds its locks across restarts. Resolve with
`COMMIT PREPARED 'gid';` or `ROLLBACK PREPARED 'gid';` only after the
transaction coordinator confirms the outcome: guessing wrong creates
inconsistency across systems. Escalate if unsure.

## Remediation (ordered, safest first)

| # | Action | Risk | Use when |
|---|---|---|---|
| 1 | **Wait**, if the root blocker is an active statement that will finish soon and the impact is tolerable | None | Short, known batch |
| 2 | Ask the owner to commit or roll back (or fix/restart the app that holds the transaction) | None | Root is `idle in transaction` and owner is reachable |
| 3 | **Cancel** the blocker's running query: `SELECT pg_cancel_backend(<PID>);` | Low | Root is `active`. Does **not** help if the root is idle in transaction |
| 4 | Cancel the **waiting DDL** instead of the blocker | Low | A migration is queuing readers/writers (DDL queue); retry it later with `lock_timeout` |
| 5 | **Terminate** the root blocker: `SELECT pg_terminate_backend(<PID>);` | Medium to high | Idle-in-transaction/aborted or runaway, and steps 2 to 4 are not possible |
| 6 | Restart the server | High | Last resort; see [database-is-down.md](database-is-down.md) |

### `pg_terminate_backend` (destructive, read first)

- **What it does:** closes the session; the open transaction is rolled back and all its locks release immediately, letting waiters proceed. The client gets `terminating connection due to administrator command`.
- **Why risky:** uncommitted work is lost; a large write rolls back (can take as long as it ran, still holding locks until done); clients without retry logic fail; ending a distributed workflow mid-way can leave external side effects.
- **Safer alternative:** `pg_cancel_backend(pid)` for active queries; ask the owner to roll back; for a stuck migration, cancel the DDL (step 4).
- **Precaution:** use the root-blocker query above and confirm pid, user, application, `xact_age`, last query; terminate one pid and re-run triage; tell application owners. Record pid and query in the timeline.

Confirm and terminate in one statement so the target cannot change between
steps (SQL):

```sql
SELECT pid, application_name, state, left(query, 60) AS last_query,
       pg_terminate_backend(pid) AS terminated
FROM pg_stat_activity
WHERE pid = <PID>
  AND state IN ('idle in transaction', 'idle in transaction (aborted)');
```

Then re-run the triage queries: the waiters should clear within seconds.
Reproduced: `pg_cancel_backend` on the idle-in-transaction root returned
`t` but left it in place; `pg_terminate_backend` removed it and the two
queued writers completed.

## Verification

```sql
SELECT count(*) AS still_waiting
FROM pg_stat_activity
WHERE cardinality(pg_blocking_pids(pid)) > 0;
```

- [ ] `still_waiting` is 0 and stays 0 for several minutes.
- [ ] Application error rate and latency back to baseline; connections no longer climbing.
- [ ] If you cancelled a migration, check its state: [failed-migration.md](failed-migration.md).
- [ ] The cause is identified (which code path opened the transaction, who ran the DDL).

## Prevention

Timeouts bound the damage. Values are illustrative; derive them from your
real transaction durations. Apply per role or per session; they affect
**new** sessions.

```sql
ALTER ROLE app_user SET lock_timeout = '5s';                          -- give up waiting for a lock
ALTER ROLE app_user SET idle_in_transaction_session_timeout = '5min'; -- server ends abandoned transactions
ALTER ROLE app_user SET statement_timeout = '30s';
```

| Control | Effect |
|---|---|
| `lock_timeout` on app roles and especially on the migration session (`SET lock_timeout = '5s';` at the top of each migration) | Failing DDL fast is better than queueing all traffic behind it. Reproduced: `ERROR: canceling statement due to lock timeout` |
| `idle_in_transaction_session_timeout` | Stuck transactions get terminated by the server, not by you at 3 a.m. |
| Short transactions: no network calls or user waits inside `BEGIN ... COMMIT` | Fewer, shorter locks |
| Consistent lock ordering across code paths | Removes the usual deadlock cause ([04-transactions/deadlocks.md](../04-transactions/deadlocks.md)) |
| `SELECT ... FOR UPDATE SKIP LOCKED` for queue-claiming | Workers do not pile up behind one row |
| `log_lock_waits = on` | Lock waits longer than `deadlock_timeout` are logged with the blocker |
| Migrations: `CREATE INDEX CONCURRENTLY`, `NOT VALID` + `VALIDATE CONSTRAINT`, retry on `lock_timeout` | Avoids long `ACCESS EXCLUSIVE` holds ([09-alembic/production-migrations.md](../09-alembic/production-migrations.md)) |
| Retry `40P01` and `40001` in the application | Deadlocks are normal under concurrency; they must be retried |

## Escalation / When to stop

- The root blocker is a **replication or autovacuum** process, or a prepared transaction whose owner is unknown: do not terminate; escalate.
- Termination "succeeds" but the session stays (rolling back a very large transaction): wait for the rollback; restarting makes crash recovery repeat the work.
- Deadlock rate is rising after a deploy: roll back or hotfix the change; escalate to the owning team with the log's two statements.
- Blocking returns within minutes after clearing: the cause (a stuck job or app bug) is still running. Stop the source before repeating the kill.
