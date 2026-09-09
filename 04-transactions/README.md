# Transactions

## What it is

How PostgreSQL groups statements into all-or-nothing units, isolates
concurrent work from other in-flight transactions, and locks the rows and
tables involved.

## Why it matters

This is where "it worked in my manual test" and "it works under
concurrent production load" diverge. A missing transaction boundary, the
wrong isolation level, or an inconsistent lock order are invisible in a
single-user test and become an incident the moment two things happen at
once.

## In this section

| Page | Covers |
|---|---|
| [transactions.md](transactions.md) | `BEGIN`/`COMMIT`/`ROLLBACK`, `SAVEPOINT` |
| [acid.md](acid.md) | Atomicity/Consistency/Isolation/Durability, tied to PostgreSQL mechanics |
| [isolation-levels.md](isolation-levels.md) | The 4 isolation levels, what each actually prevents in PostgreSQL |
| [locking.md](locking.md) | Row/table lock modes, `SKIP LOCKED`, advisory locks |
| [deadlocks.md](deadlocks.md) | Detection, `40P01`, avoidance, retry |

## Where to go next

- The statements a transaction wraps around: see
  [02-sql-fundamentals/insert-update-delete.md](../02-sql-fundamentals/insert-update-delete.md).
- Adding a constraint/foreign key to a large table without a long lock:
  see [03-database-design/foreign-keys.md](../03-database-design/foreign-keys.md#production-considerations).
- Diagnosing lock contention or a slow query live: see
  [05-performance/](../05-performance/) and
  [14-observability/pg-locks.md](../14-observability/pg-locks.md).
- Mid-incident, blocked queries right now: see
  [15-production-runbooks/lock-contention.md](../15-production-runbooks/lock-contention.md).
- Claiming rows safely across concurrent workers (agent task queues): see
  [11-agentic-ai/](../11-agentic-ai/).
