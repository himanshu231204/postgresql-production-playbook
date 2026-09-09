# Isolation Levels

## What it is

How much of other transactions' concurrent, uncommitted-or-recently-committed
work a transaction is allowed to see.

## Why it matters

The default isolation level is fine for most application code — but
anything doing "read a value, then write based on it" under concurrent
load (balance transfers, inventory decrements, uniqueness checks not
backed by a constraint) needs to understand what its isolation level
actually protects against.

## Syntax

```sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
-- ...
COMMIT;

-- Or in one line:
BEGIN ISOLATION LEVEL SERIALIZABLE;
```

## The four SQL-standard levels, and what PostgreSQL actually does

| Level | Dirty read | Nonrepeatable read | Phantom read | Serialization anomaly | PostgreSQL's actual behavior |
|---|---|---|---|---|---|
| `READ UNCOMMITTED` | Possible (standard) | Possible | Possible | Possible | **Not implemented** — PostgreSQL treats this as `READ COMMITTED`; it never allows dirty reads at all |
| `READ COMMITTED` (default) | Prevented | Possible | Possible | Possible | Each statement sees a fresh snapshot as of when *that statement* started |
| `REPEATABLE READ` | Prevented | Prevented | Prevented | Possible | One snapshot for the *whole transaction* (true snapshot isolation) — stricter than the SQL standard requires at this level, which only mandates preventing the first two |
| `SERIALIZABLE` | Prevented | Prevented | Prevented | Prevented | Serializable Snapshot Isolation (SSI) — behaves as if transactions ran one at a time, at the cost of possible serialization failures under concurrency |

**Dirty read**: seeing another transaction's uncommitted change.
**Nonrepeatable read**: re-running the same query in one transaction and
getting a different answer because another transaction committed in
between. **Phantom read**: a range query returning different *rows*
(not just different values) on a second run within the same transaction.
**Serialization anomaly**: the combined effect of concurrent transactions
couldn't have resulted from running them in *any* serial order — the
subtlest and most dangerous, since each transaction looks correct in
isolation.

## Production usage

`READ COMMITTED` is the right default for most CRUD application code —
each statement seeing a fresh snapshot matches how most code implicitly
expects the database to behave.

Reach for `REPEATABLE READ` or `SERIALIZABLE` specifically for
"read-then-write based on what you read" logic that a `CHECK`/`UNIQUE`
constraint can't express directly — e.g. "don't let the total across
several rows exceed a limit." Both can fail a transaction with a
`40001` (`serialization_failure`) error when a real conflict is detected
— **the application must catch this and retry the whole transaction**,
not treat it as a fatal error:

```python
for attempt in range(3):
    try:
        with conn.transaction(isolation_level="serializable"):
            run_transfer(conn, from_id, to_id, amount)
        break
    except SerializationFailure:
        if attempt == 2:
            raise
        continue  # retry from the top
```

## Common mistakes

- Assuming `REPEATABLE READ` in PostgreSQL matches the SQL standard's
  minimum definition for that level — PostgreSQL's implementation is
  stricter (it also blocks phantom reads).
- Using `SERIALIZABLE` without a retry loop in application code — a
  `40001` is an expected, normal outcome under concurrency, not a bug.
- Reaching for a stricter isolation level to fix a race condition that a
  `UNIQUE` constraint or `SELECT ... FOR UPDATE` (see
  [locking.md](locking.md)) would solve more directly and cheaply.

## Performance considerations

`SERIALIZABLE` has real overhead (tracking read/write dependencies
between concurrent transactions) and can abort transactions that would
have been fine under `READ COMMITTED` — reserve it for the specific
transactions that need it, not as a database-wide default.

## Quick revision

- PostgreSQL has no true `READ UNCOMMITTED` — it's `READ COMMITTED`.
- `READ COMMITTED` (default): fresh snapshot per statement.
- `REPEATABLE READ`: one snapshot for the whole transaction; blocks
  phantom reads too (stricter than the SQL standard requires).
- `SERIALIZABLE`: full protection, but must be paired with a retry loop
  for `40001` serialization failures.
