# Transactions

## What it is

A group of statements that either all take effect together (`COMMIT`) or
none do (`ROLLBACK`).

## Why it matters

Without an explicit transaction, each statement commits on its own. If a
multi-step write (e.g. "debit one account, credit another") fails halfway
through with no transaction wrapping it, the database is left in a state
that never should have existed.

## Syntax

```sql
BEGIN;
UPDATE accounts SET balance = balance - 100 WHERE id = 1;
UPDATE accounts SET balance = balance + 100 WHERE id = 2;
COMMIT;   -- or ROLLBACK to undo both
```

Every statement outside an explicit `BEGIN` runs in its own
implicit, single-statement transaction — it's still atomic, just scoped
to one statement.

### Savepoints: partial rollback within a transaction

```sql
BEGIN;
INSERT INTO orders (customer_id) VALUES (1);
SAVEPOINT before_items;
INSERT INTO order_items (order_id, product_id) VALUES (1, 999);  -- fails: no such product
ROLLBACK TO SAVEPOINT before_items;   -- undo back to the savepoint, transaction stays open
-- ... insert valid items instead ...
COMMIT;
```

`RELEASE SAVEPOINT name` discards a savepoint you no longer need without
rolling back to it.

## Production usage

**A failed statement poisons the rest of the transaction.** Once any
statement in a transaction errors, PostgreSQL refuses every subsequent
statement in that transaction (`current transaction is aborted, commands
ignored until end of transaction block`) until you `ROLLBACK` — or
`ROLLBACK TO SAVEPOINT` a point before the failure. Client libraries and
ORMs generally handle this automatically per request; hand-rolled scripts
issuing raw SQL need to handle it explicitly.

**`SELECT ... FOR UPDATE SKIP LOCKED`** inside a transaction is the
standard pattern for multiple workers safely claiming rows from a queue
without waiting on each other — covered fully in
[locking.md](locking.md#claiming-work-safely-select--for-update-skip-locked).

## Common mistakes

- Leaving a transaction open ("idle in transaction") while doing
  slow, unrelated work (an HTTP call, waiting on user input) — every lock
  it's holding stays held the whole time. See
  [15-production-runbooks/lock-contention.md](../15-production-runbooks/lock-contention.md).
- Not handling the "current transaction is aborted" state in scripts that
  issue raw SQL — the connection looks alive but every statement fails
  until a `ROLLBACK`.
- Forgetting a transaction at all for a multi-statement write that must
  succeed or fail together.

## Security considerations

Nothing transaction-specific beyond what already applies to the
statements inside it — see
[02-sql-fundamentals/select.md](../02-sql-fundamentals/select.md#security-considerations).

## Performance considerations

Keep transactions as short as possible. A long-running transaction holds
its locks for its entire duration and, in PostgreSQL's MVCC model, also
prevents `VACUUM` from cleaning up rows that became dead after that
transaction's snapshot started — see
[05-performance/vacuum.md](../05-performance/vacuum.md).

## AI/agentic use case

Recording an agent's `tool_call` result alongside its `workflow_state`
update in the same transaction keeps them consistent — either both
happen or neither does, so a crash between the two can't leave the
workflow state pointing at a tool call that was never actually recorded.
See [AGENTS.md](../AGENTS.md#12-agentic-ai-database-rules).

## Troubleshooting

| Symptom | Cause |
|---|---|
| `ERROR: current transaction is aborted, commands ignored until end of transaction block` | An earlier statement in this transaction failed; `ROLLBACK` (or roll back to a savepoint before it) |
| A lock seems to be held with no query running | An "idle in transaction" connection — see [locking.md](locking.md) and [15-production-runbooks/lock-contention.md](../15-production-runbooks/lock-contention.md) |

## Quick revision

- `BEGIN` / `COMMIT` / `ROLLBACK` for multi-statement atomicity; every
  statement is implicitly its own transaction otherwise.
- `SAVEPOINT` allows partial rollback without abandoning the whole
  transaction.
- One failed statement blocks the rest of the transaction until rollback.
- Keep transactions short — an idle or long-running one holds locks and
  blocks vacuum cleanup.
