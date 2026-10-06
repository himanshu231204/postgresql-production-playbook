# pg_locks and Blocker Chains

PostgreSQL 16; queries executed against a reproduced blocking scenario.
Lock modes and application-side avoidance are in
[../04-transactions/locking.md](../04-transactions/locking.md) and
[../04-transactions/deadlocks.md](../04-transactions/deadlocks.md);
the incident procedure is
[../15-production-runbooks/lock-contention.md](../15-production-runbooks/lock-contention.md).

## What it is

`pg_locks` lists every lock held or awaited: one row per lock per backend.
`pg_blocking_pids(pid)` returns the PIDs blocking a given session.

## Why it matters

"The query just hangs" is usually a lock wait. `pg_stat_activity` shows
*that* a session waits (`wait_event_type = 'Lock'`); `pg_locks` and
`pg_blocking_pids()` show *who* is in the way. Use `pg_blocking_pids()` to
find blockers; do not derive them by hand from `pg_locks`.

## Key columns of `pg_locks`

| Column | Meaning |
|---|---|
| `locktype` | `relation`, `transactionid`, `tuple`, `virtualxid`, `advisory`, ... |
| `mode` | Lock mode, e.g. `RowExclusiveLock`, `AccessExclusiveLock`, `ShareLock` |
| `granted` | `true` = held, `false` = waiting |
| `relation` | OID of the table/index (cast `::regclass` for the name) |
| `transactionid` | For `transactionid` locks: the transaction being waited on |
| `pid` | Backend holding or awaiting the lock |

A row-level wait appears as a waiting `transactionid` lock (waiting for
the other transaction to finish), plus a `tuple` lock when several
sessions queue for the same row. Row locks themselves are not listed
individually in `pg_locks`.

## Queries (SQL)

Who is waiting and for what:

```sql
SELECT l.pid, l.locktype, l.mode, l.granted,
       l.relation::regclass AS relation, l.transactionid,
       a.state, left(a.query, 60) AS query
FROM pg_locks l
JOIN pg_stat_activity a USING (pid)
WHERE NOT l.granted;
```

Blocked sessions and the PIDs blocking them:

```sql
SELECT a.pid, pg_blocking_pids(a.pid) AS blocked_by,
       a.wait_event_type, a.wait_event,
       now() - a.query_start AS waiting_for,
       left(a.query, 60) AS query
FROM pg_stat_activity a
WHERE cardinality(pg_blocking_pids(a.pid)) > 0;
```

Output from the test scenario (session 2354 holds an open transaction
that updated row 1; four sessions queue behind it):

```text
 pid  |    blocked_by    | wait_event_type |  wait_event   |   waiting_for   | query
------+------------------+-----------------+---------------+-----------------+----------------------------------
 2466 | {2354}           | Lock            | transactionid | 00:00:20.666355 | ...UPDATE accounts ... WHERE id=1
 2877 | {2466}           | Lock            | tuple         | 00:00:03.023603 | ...UPDATE accounts ... WHERE id=1
 2897 | {2466,2877}      | Lock            | tuple         | 00:00:02.013771 | ...UPDATE accounts ... WHERE id=1
 2898 | {2466,2877,2897} | Lock            | tuple         | 00:00:02.008988 | ...UPDATE accounts ... WHERE id=1
```

Root blockers (blockers that are themselves not waiting) with how many
sessions they hold up — this is the list to act on:

```sql
SELECT b.pid, b.usename, b.application_name, b.state,
       now() - b.xact_start AS xact_age,
       count(*) AS sessions_blocked,
       left(b.query, 60) AS last_query
FROM pg_stat_activity w
CROSS JOIN LATERAL unnest(pg_blocking_pids(w.pid)) AS blocker(pid)
JOIN pg_stat_activity b ON b.pid = blocker.pid
WHERE cardinality(pg_blocking_pids(b.pid)) = 0
GROUP BY b.pid, b.usename, b.application_name, b.state, b.xact_start, b.query
ORDER BY sessions_blocked DESC;
```

```text
 pid  | usename  | application_name |        state        |    xact_age     | sessions_blocked | last_query
------+----------+------------------+---------------------+-----------------+------------------+---------------------------------
 2354 | postgres | psql             | active              | 00:00:29.727926 |                1 | SELECT pg_sleep(40)
 2498 | postgres | psql             | idle in transaction | 00:00:18.638134 |                1 | BEGIN; SELECT 1 FROM accounts ...
```

`sessions_blocked` counts direct waiters only (here 1 for 2354, since the
others queue behind 2466); the blocker's own `state` and `xact_age`
matter more. An `idle in transaction` root blocker means the application
opened a transaction and stopped.

Locks held on one table:

```sql
SELECT l.pid, l.mode, l.granted
FROM pg_locks l
WHERE l.locktype = 'relation' AND l.relation = 'accounts'::regclass
ORDER BY l.granted, l.pid;
```

Replace `accounts` with the table name. Ordinary DML takes
`RowExclusiveLock` on the table, which does not conflict with other DML;
the dangerous ones are `ShareLock`, `AccessExclusiveLock` (most `ALTER
TABLE`, `VACUUM FULL`, `TRUNCATE`) held or queued.

## Resolving a blocker

1. Identify the root blocker (query above) and look at its `state`, `xact_age`, `application_name`.
2. If it is a running query that should not run: `SELECT pg_cancel_backend(<pid>);`
3. If it is `idle in transaction`: cancel does nothing; the owning application must commit/rollback, or `SELECT pg_terminate_backend(<pid>);`

`pg_terminate_backend` rolls back that transaction's uncommitted work and
is not reversible; precautions (verify PID, check what the transaction was
doing, prefer cancel first) are in
[pg-stat-activity.md](pg-stat-activity.md#cancelling-and-terminating-sessions-destructive).
Never terminate a session running a migration without checking what it
changed first.

## Logging lock waits and preventing pile-ups

- `log_lock_waits = on` logs a message when a session waits longer than `deadlock_timeout` (default `1s`); changing it needs superuser, reload only.
- `lock_timeout` (default `0`, disabled) makes a statement fail instead of waiting indefinitely. Set it in migration sessions: `SET lock_timeout = '5s';` (example value) so a DDL waiting for `ACCESS EXCLUSIVE` does not block all traffic queued behind it. See [../09-alembic/](../09-alembic/).
- Deadlocks: `pg_stat_database.deadlocks` counts them; details are in the server log. See [../04-transactions/deadlocks.md](../04-transactions/deadlocks.md).

## Common mistakes

- Killing the blocked sessions instead of the root blocker; they re-queue.
- Forgetting that a queued `ALTER TABLE` blocks everything behind it, even plain `SELECT`s.
- Ignoring `idle in transaction` blockers; they look harmless in CPU graphs.
- Running `SELECT ... FROM pg_locks` in a hot loop on a very busy server; it takes brief internal locks. Sample at an interval.

## Quick revision

- `pg_blocking_pids(pid)` is the answer to "who blocks me".
- Act on root blockers (not themselves waiting).
- Cancel stops a query; only terminate frees an idle-in-transaction session's locks.
- Prevent with `lock_timeout`, `idle_in_transaction_session_timeout`, short transactions.
