# Locking

## What it is

The mechanism PostgreSQL uses to prevent concurrent transactions from
making conflicting changes to the same row(s) or table at once.

## Why it matters

Locking is what makes concurrent writes safe — and also the most common
source of "why is this query just hanging" incidents. See
[15-production-runbooks/lock-contention.md](../15-production-runbooks/lock-contention.md)
for the incident-response side of this page.

## Row-level locks

Taken explicitly with a `SELECT ... FOR ...` clause, or implicitly by
`UPDATE`/`DELETE`:

| Mode | Syntax | Blocks other transactions from... |
|---|---|---|
| `FOR UPDATE` | `SELECT ... FOR UPDATE` | Any other lock on these rows, including another `FOR UPDATE` |
| `FOR NO KEY UPDATE` | `SELECT ... FOR NO KEY UPDATE` | Same as `FOR UPDATE`, except it doesn't conflict with `FOR KEY SHARE` — taken implicitly by a plain `UPDATE` that doesn't touch a key column referenced by a foreign key |
| `FOR SHARE` | `SELECT ... FOR SHARE` | Any update/delete on these rows; does not block other `FOR SHARE` readers |
| `FOR KEY SHARE` | `SELECT ... FOR KEY SHARE` | Only a change to the key columns themselves; taken implicitly when another table's row references this one via foreign key |

```sql
BEGIN;
SELECT balance FROM accounts WHERE id = 1 FOR UPDATE;  -- lock this row before reading it
UPDATE accounts SET balance = balance - 100 WHERE id = 1;
COMMIT;
```

Locking the row with `FOR UPDATE` *before* deciding what to write based
on its current value is what closes the race condition between two
concurrent transactions both reading the same stale balance.

## Claiming work safely: `SELECT ... FOR UPDATE SKIP LOCKED`

The standard pattern for multiple workers pulling jobs from a queue table
without waiting on each other or double-processing a row:

```sql
BEGIN;
SELECT id FROM tasks
WHERE status = 'pending'
ORDER BY created_at
LIMIT 1
FOR UPDATE SKIP LOCKED;   -- skip rows another worker already has locked, instead of waiting

UPDATE tasks SET status = 'in_progress' WHERE id = <claimed_id>;
COMMIT;
```

Without `SKIP LOCKED`, a second worker's `SELECT ... FOR UPDATE` would
simply wait for the first worker's lock to release, then claim the same
row anyway (or block indefinitely) — `SKIP LOCKED` lets it move on to a
different, unclaimed row instead.

## Table-level locks

Taken implicitly by DDL (`ALTER TABLE`, etc.) or explicitly with `LOCK
TABLE`. PostgreSQL has eight table lock modes of increasing strictness
(from `ACCESS SHARE`, taken by a plain `SELECT`, up to `ACCESS
EXCLUSIVE`, taken by most `ALTER TABLE` forms and `DROP TABLE`) — the
practical takeaway is that schema changes on a live table can block
reads/writes, which is why
[03-database-design/foreign-keys.md](../03-database-design/foreign-keys.md#production-considerations)
and [03-database-design/indexes.md](../03-database-design/indexes.md#building-an-index-without-blocking-writes)
cover `NOT VALID`/`VALIDATE CONSTRAINT` and `CREATE INDEX CONCURRENTLY`
as ways to avoid the strictest lock modes on a production table.

## Advisory locks

Application-defined locks with no connection to any specific row or
table — useful for coordinating something outside normal row/table
locking, like ensuring only one instance of a scheduled job runs at a
time:

```sql
SELECT pg_try_advisory_lock(12345);  -- returns true if acquired, false if already held
-- ... do the exclusive work ...
SELECT pg_advisory_unlock(12345);
```

`pg_advisory_lock` blocks until it can acquire the lock;
`pg_try_advisory_lock` returns immediately with `true`/`false`. The
integer key is whatever the application agrees it means — PostgreSQL
doesn't attach any table/row semantics to it.

## Common mistakes

- Reading a value, deciding what to write based on it in application
  code, then writing — without locking the row first (`FOR UPDATE`) — a
  classic read-then-write race condition.
- Using `FOR UPDATE` in a queue-claiming query without `SKIP LOCKED`,
  causing every worker to queue up behind whichever one claimed first.
- Leaving a transaction "idle in transaction" while holding a row or
  table lock — see
  [transactions.md](transactions.md#common-mistakes).
- Running schema-changing DDL against a busy production table without
  considering which lock mode it takes (see
  [03-database-design/foreign-keys.md](../03-database-design/foreign-keys.md)).

## AI/agentic use case

`SELECT ... FOR UPDATE SKIP LOCKED` against a `tasks`/`workflow_state`
table is the standard way to let multiple agent worker processes safely
pull the next unclaimed step without coordinating out-of-band. See
[AGENTS.md](../AGENTS.md#12-agentic-ai-database-rules) on concurrency and
[11-agentic-ai/workflow-state.md](../11-agentic-ai/workflow-state.md).

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| A query hangs with no error | Waiting on a lock held by another transaction — see [14-observability/pg-locks.md](../14-observability/pg-locks.md) to find who's holding it |
| Multiple queue workers all block on the same row | Missing `SKIP LOCKED` on the claiming query |

## Quick revision

- `FOR UPDATE` before writing based on a value you just read, to close
  the read-then-write race.
- `SKIP LOCKED` for concurrent queue-style row claiming.
- Advisory locks for app-level coordination with no table/row involved.
- Schema DDL takes table-level locks — see the foreign-key/index pages
  for how to avoid blocking production writes.
