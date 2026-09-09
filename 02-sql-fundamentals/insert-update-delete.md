# INSERT, UPDATE, DELETE

## What it is

The statements that write, modify, and remove rows, plus PostgreSQL's
`ON CONFLICT` upsert clause and the `RETURNING` clause shared by all three.

## Why it matters

These are the statements that can lose or corrupt production data if
written carelessly — a missing `WHERE` on `UPDATE`/`DELETE` is one of the
most common serious incidents in this repository's
[15-production-runbooks/](../15-production-runbooks/).

## Syntax

```sql
INSERT INTO table (col1, col2) VALUES (v1, v2), (v3, v4)
  RETURNING id;

UPDATE table SET col1 = v1 WHERE condition
  RETURNING id, col1;

DELETE FROM table WHERE condition
  RETURNING id;
```

`RETURNING` gives back the affected rows without a separate `SELECT` —
useful for getting a generated ID immediately after an `INSERT`.

## Upserts: `INSERT ... ON CONFLICT`

```sql
INSERT INTO users (email, name)
VALUES ('a@example.com', 'A')
ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name;

-- Or, to just skip a conflicting row:
INSERT INTO users (email, name)
VALUES ('a@example.com', 'A')
ON CONFLICT (email) DO NOTHING;
```

`ON CONFLICT (email)` targets a unique constraint/index on `email`.
`EXCLUDED` refers to the row that was proposed for insertion. PostgreSQL
15+ also has a `MERGE` statement, which is more powerful for
conditionally inserting/updating/deleting in one statement based on
comparing against another table — reach for `MERGE` when the logic goes
beyond a single-table upsert; `ON CONFLICT` remains simpler for the common
case.

## Join-based `UPDATE`/`DELETE`

```sql
UPDATE orders o
SET status = 'cancelled'
FROM customers c
WHERE o.customer_id = c.id AND c.is_banned = true;

DELETE FROM sessions s
USING users u
WHERE s.user_id = u.id AND u.deleted_at IS NOT NULL;
```

## Common mistakes

- Running `UPDATE`/`DELETE` without a `WHERE` clause against a production
  table — this affects every row. See
  [AGENTS.md](../AGENTS.md#18-production-safety-in-content).
- Using `TRUNCATE` when a filtered `DELETE` was actually needed —
  `TRUNCATE` cannot target a subset of rows and is not transaction-safe
  the same way on tables referenced by foreign keys without `CASCADE`.
- Assuming `ON CONFLICT DO UPDATE` never fires if nothing actually
  changed — it still executes the `UPDATE` (and any `UPDATE` triggers)
  even when the new values match the old ones, unless you add a `WHERE`
  clause on the `DO UPDATE` to skip no-op updates.
- Doing thousands of single-row `INSERT`s in a loop instead of one
  multi-row `INSERT` or `COPY` — see "Performance considerations."

## Security considerations

Parameterize every value, including in `ON CONFLICT` and join-based
`UPDATE`/`DELETE` — the same injection risk as `SELECT` applies (see
[select.md](select.md#security-considerations)).

## Performance considerations

- Batch writes: one multi-row `INSERT` (or `COPY` for bulk loads) is far
  faster than many single-row `INSERT`s, because each statement has
  per-statement overhead (planning, WAL flush behavior, round trips).
- A large, unbatched `DELETE`/`UPDATE` holds row locks for its whole
  duration and generates a burst of dead tuples for autovacuum to clean up
  — see [05-performance/vacuum.md](../05-performance/vacuum.md). Batch
  large deletes into smaller transactions in production.

## AI/agentic use case

`ON CONFLICT DO NOTHING`/`DO UPDATE` is the standard pattern for making an
agent's tool-call or workflow-step writes idempotent under retry — key the
unique constraint on an idempotency key (e.g. `tool_call_id`) so a retried
call doesn't double-apply. See
[AGENTS.md](../AGENTS.md#12-agentic-ai-database-rules) and
[11-agentic-ai/tool-calls.md](../11-agentic-ai/tool-calls.md).

## Troubleshooting

| Symptom | Cause |
|---|---|
| `duplicate key value violates unique constraint` | An `INSERT` without `ON CONFLICT` hit an existing unique/primary key value |
| `UPDATE`/`DELETE` affected far more rows than expected | Missing or too-broad `WHERE` clause — check before running, especially interactively |
| `ON CONFLICT DO UPDATE` requires a WHERE ... ON CONFLICT | The conflict target doesn't match an existing unique constraint/index on those columns |

## Quick revision

- Always double-check `WHERE` before running `UPDATE`/`DELETE` in production.
- `INSERT ... ON CONFLICT (col) DO UPDATE/DO NOTHING` is the standard upsert; `MERGE` (PG 15+) for multi-outcome logic.
- `RETURNING` avoids a round-trip `SELECT` after a write.
- Batch bulk writes; don't loop single-row statements.
