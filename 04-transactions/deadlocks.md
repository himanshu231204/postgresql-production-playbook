# Deadlocks

## What it is

A cycle of transactions each waiting on a lock the other holds, with no
possible way for either to proceed.

## Why it matters

Unlike ordinary lock waiting (which resolves once the holder commits or
rolls back), a deadlock cycle never resolves on its own — PostgreSQL has
to detect it and forcibly abort one side.

## How PostgreSQL handles it

```
Transaction A: locks row 1, then waits for row 2 (held by B)
Transaction B: locks row 2, then waits for row 1 (held by A)
```

PostgreSQL doesn't check for deadlocks immediately when a transaction
starts waiting on a lock — it waits `deadlock_timeout` (default: 1
second) first, then checks whether the wait is part of a cycle. If it
is, it aborts one of the transactions (the "victim") with:

```
ERROR: deadlock detected (SQLSTATE 40P01)
```

and releases that transaction's locks, letting the other one proceed.
The aborted transaction's changes are rolled back entirely — the
application must retry it, the same way it would for a `40001`
serialization failure (see
[isolation-levels.md](isolation-levels.md#production-usage)).

## Reading a deadlock log entry

PostgreSQL's log entry for a deadlock names the conflicting processes,
the locks each was waiting for and holding, and the queries involved —
this is usually enough to identify which two code paths are taking the
same two locks in a different order.

## Avoiding deadlocks

The root cause is almost always **inconsistent lock ordering** across
different code paths that touch the same rows/tables. Fixes, in order of
preference:

1. **Always acquire locks in the same order** across every code path
   that touches more than one of the same rows/tables — e.g. always lock
   the lower-numbered account ID first in a funds-transfer function,
   regardless of which account is the "source."
2. **Keep transactions short** — the shorter the window between acquiring
   a lock and releasing it, the smaller the chance another transaction's
   lock-wait overlaps with it.
3. **Take the most restrictive lock you'll need up front**, rather than
   escalating from a weaker lock to a stronger one partway through — two
   transactions escalating in different orders is itself a common
   deadlock pattern.

## Common mistakes

- Two code paths updating the same two tables/rows in opposite order
  (A-then-B in one function, B-then-A in another) — the classic deadlock
  setup.
- Treating a `40P01` error as a bug to fix by adding more locking, rather
  than a normal, expected outcome under concurrency that the application
  must retry.
- Assuming a deadlock means data corruption — it doesn't; the aborted
  transaction is fully rolled back, and the database stays consistent.

## Production considerations

A deadlock rate that's low and handled with retries is normal for a
busy, concurrent system. A *rising* deadlock rate usually points to a
recent code change that introduced a new lock-ordering inconsistency —
check recent deploys before assuming it's a pre-existing, tolerable
background rate. See
[15-production-runbooks/lock-contention.md](../15-production-runbooks/lock-contention.md)
for the live-incident diagnostic steps.

## Quick revision

- A deadlock is a lock-wait cycle; PostgreSQL detects it after
  `deadlock_timeout` (default 1s) and aborts one side with `40P01`.
- Fix the root cause: make every code path acquire shared locks in the
  same order.
- The application must retry an aborted (`40P01`) transaction, same as a
  `40001` serialization failure.
