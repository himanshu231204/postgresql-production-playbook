# pg_stat_activity

All queries below: PostgreSQL 16, executed in `psql`. Without
`pg_read_all_stats` (or superuser) other roles' `query`, `state`, and
wait columns are NULL.

## What it is

A system view with one row per server process: client backends and
background processes (`backend_type`). It is the first stop for "what is
the database doing right now".

## Why it matters

It exposes stuck, long-running, and idle-in-transaction sessions, and which
sessions are waiting on a lock, I/O, or the client. Pair with
[pg-locks.md](pg-locks.md) for blockers and
[../15-production-runbooks/connection-exhaustion.md](../15-production-runbooks/connection-exhaustion.md)
when connections run out.

## Key columns

| Column | Meaning |
|---|---|
| `pid` | Backend process ID; the argument to `pg_cancel_backend`/`pg_terminate_backend` |
| `state` | `active`, `idle`, `idle in transaction`, `idle in transaction (aborted)`, `fastpath function call`, `disabled` |
| `wait_event_type`, `wait_event` | What the backend is waiting on (`Lock`, `LWLock`, `IO`, `Client`, `Timeout`, `Activity`...); NULL while running on CPU |
| `xact_start` | Start of the current transaction |
| `query_start` | Start of the current (or last) query |
| `state_change` | When `state` last changed — age of an idle state |
| `backend_type` | `client backend`, `autovacuum worker`, `walwriter`, ... Filter to `'client backend'` for application sessions |
| `application_name` | Set by the client; set it per service so sessions are attributable |
| `backend_xmin` | Oldest snapshot this session holds; old values block VACUUM cleanup |

`query` shows the current query, or the **last** query when `state` is
not `active`. Text is truncated to `track_activity_query_size` (1024 bytes
by default; changing it needs a restart).

## Queries (SQL)

Current client sessions:

```sql
SELECT pid, usename, application_name, client_addr, state,
       wait_event_type, wait_event, xact_start, query_start,
       left(query, 80) AS query
FROM pg_stat_activity
WHERE backend_type = 'client backend' AND pid <> pg_backend_pid();
```

Sessions by state:

```sql
SELECT state, count(*)
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY state ORDER BY count(*) DESC;
```

Longest-running active queries:

```sql
SELECT pid, usename, now() - query_start AS runtime,
       wait_event_type, wait_event, left(query, 80) AS query
FROM pg_stat_activity
WHERE state = 'active' AND backend_type = 'client backend'
  AND pid <> pg_backend_pid()
ORDER BY query_start
LIMIT 20;
```

Idle in transaction (holds locks and a snapshot, does no work):

```sql
SELECT pid, usename, application_name,
       now() - xact_start  AS xact_age,
       now() - state_change AS idle_in_tx_for,
       left(query, 80) AS last_query
FROM pg_stat_activity
WHERE state IN ('idle in transaction', 'idle in transaction (aborted)')
ORDER BY state_change;
```

Example output from a test session that ran `BEGIN; SELECT ... FOR UPDATE`
and then stopped:

```text
 pid  | usename  | application_name |    xact_age    | idle_in_tx_for  |                     last_query
------+----------+------------------+----------------+-----------------+-----------------------------------------------------
 2498 | postgres | psql             | 00:00:18.66291 | 00:00:18.661883 | BEGIN; SELECT 1 FROM accounts WHERE id=2 FOR UPDATE
```

Connection usage against the limit:

```sql
SELECT count(*) AS client_backends,
       current_setting('max_connections')::int AS max_connections,
       current_setting('superuser_reserved_connections')::int AS superuser_reserved,
       round(100.0 * count(*) / current_setting('max_connections')::int, 1) AS pct_used
FROM pg_stat_activity
WHERE backend_type = 'client backend';
```

Connections per role/application/state (find the service that leaks):

```sql
SELECT usename, application_name, state, count(*)
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY 1, 2, 3 ORDER BY count(*) DESC;
```

Sessions holding old snapshots (blocks cleanup, see
[../05-performance/vacuum.md](../05-performance/vacuum.md)):

```sql
SELECT pid, usename, state, backend_xmin, age(backend_xmin) AS xmin_age
FROM pg_stat_activity
WHERE backend_xmin IS NOT NULL
ORDER BY age(backend_xmin) DESC;
```

## Reading `wait_event_type`

| Value | Typical reading |
|---|---|
| NULL | Running on CPU (or between waits) |
| `Lock` | Waiting for a heavyweight lock — go to [pg-locks.md](pg-locks.md) |
| `LWLock` | Internal contention (buffer/WAL/etc.); look at `wait_event` |
| `IO` | Waiting on disk read/write |
| `Client` | Waiting for the client (`ClientRead` on an idle-in-transaction session = application is not sending the next command) |
| `Timeout` | Sleeping (`PgSleep`), vacuum delay, etc. |

Wait events are a sample of one instant; repeat the query a few times
before drawing conclusions. Full list: PostgreSQL docs, "Wait Event
Types" in the monitoring-stats chapter.

## Cancelling and terminating sessions (destructive)

| Function | Effect | Reversible |
|---|---|---|
| `pg_cancel_backend(pid)` | Sends SIGINT: cancels the **current query**; the session and its transaction stay open | Client may retry |
| `pg_terminate_backend(pid)` | Sends SIGTERM: **closes the connection**; the open transaction is rolled back | No |

Both return `true` when the signal was sent, not when the session has
finished stopping. Verified behavior on PostgreSQL 16:

```sql
SELECT pg_cancel_backend(2498);    -- returns t, but the session was idle in transaction ...
SELECT state FROM pg_stat_activity WHERE pid = 2498;
--  idle in transaction            -- ... and is still idle in transaction: nothing to cancel
SELECT pg_terminate_backend(2498); -- returns t; connection closed, locks released
```

Cancel only affects a running query; it does nothing to an
idle-in-transaction session. Releasing that session's locks requires
terminate.

Risks and precautions before running either:

- A terminate rolls back all uncommitted work in that transaction. Rollback of a large write transaction can itself take time.
- Confirm the `pid` and its role/application first (`SELECT pid, usename, application_name, state, left(query, 80) FROM pg_stat_activity WHERE pid = 12345;`). PIDs are reused; never copy a PID from old output.
- Never target `backend_type <> 'client backend'` (autovacuum workers, WAL sender) or the replication/migration session you do not own, without understanding the consequence. Never terminate a session performing a migration or restore without checking its progress.
- Prefer cancel first for a running query; use terminate for idle-in-transaction or a session that ignores cancel.
- Do not run bulk forms (`SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE ...`) without first running the same `WHERE` as a plain `SELECT` to review the rows, and always exclude your own session with `pid <> pg_backend_pid()`.
- Safer long-term alternatives: `statement_timeout`, `lock_timeout`, and `idle_in_transaction_session_timeout` (all default `0` = disabled). Set them per role or per application, for example `ALTER ROLE app_user SET idle_in_transaction_session_timeout = '60s';` (value is an example; size it from your own transaction durations).

Permissions: superuser, a role that is a member of the target's role, or
`pg_signal_backend` (which cannot signal superuser sessions).

## Common mistakes

- Treating `query` of an `idle` session as what it is running; it is the last query.
- Counting all rows (including background workers) against `max_connections`; filter `backend_type = 'client backend'`.
- Terminating the blocked session instead of its blocker (see [pg-locks.md](pg-locks.md)).
- Ignoring `idle in transaction` because it uses no CPU; it holds locks and prevents VACUUM cleanup.

## Quick revision

- `state = 'idle in transaction'` + old `xact_start` = application bug or missing commit.
- `wait_event_type = 'Lock'` = go to `pg_blocking_pids()`.
- Cancel = stop query; terminate = drop connection and roll back. Check the PID first.
- Use timeouts to prevent, not terminate to cure.
