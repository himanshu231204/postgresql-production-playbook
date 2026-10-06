# Workflow State

## What it is

Durable checkpoints and a job queue so an agent run can be resumed after a
crash, retried with backoff, and processed by many workers without
double-execution. Tables: `workflow_state`, `tasks`, `agent_runs`.

## Why it matters

An in-memory agent loses its place when a pod restarts, a deploy happens,
or an LLM call times out. If every step's outcome is committed, a new
worker reads the checkpoint and continues from the next step instead of
redoing (and re-billing, re-emailing) earlier ones.

## Checkpoint model

One `workflow_state` row per run:

| Column | Meaning |
|---|---|
| `workflow` | Which graph/flow this run executes |
| `step` | Next step to execute (not the last completed one) |
| `state` | Small JSONB working data; `CHECK (jsonb_typeof(state) = 'object' AND pg_column_size(state) < 65536)` |
| `version` | Optimistic-lock counter ([agent-state.md](agent-state.md#optimistic-concurrency)) |

Resume procedure:

1. Claim the run (queue claim or `WHERE status = 'queued' AND version = $n`).
2. `SELECT step, state, version FROM workflow_state WHERE run_id = $1;`
3. Find unfinished tool calls: `SELECT idempotency_key, status FROM tool_calls WHERE run_id = $1 AND status IN ('pending','running');`
4. Re-execute from `step`. Each tool call goes through its idempotency key ([tool-calls.md](tool-calls.md)), so a step that already succeeded returns its stored result instead of running again.
5. Commit the step result and the new checkpoint in one transaction.

Design rules:

- Make steps deterministic given `(state, stored tool results)`. LLM output is not deterministic: store the model's decision (the tool call row, the assistant message) before acting on it, and on resume reuse the stored decision rather than asking again.
- Keep `state` small: pointers (ids) to `messages` and `tool_calls`, counters, flags. Large artifacts belong in their own tables or object storage. A JSONB value above about 2 kB is stored out of line (TOAST), and every update rewrites the whole value.
- Do not keep history in `state`. History is `messages`, `tool_calls`, `audit_logs`.

## Claiming tasks

The `tasks` table is a lease-based queue. **PostgreSQL SQL**, PostgreSQL 16;
tested with four concurrent workers in
[task_claiming.py](../examples/production-agent-db/demo/task_claiming.py).

```sql
-- Claim one task. Short transaction; the lease covers processing time.
UPDATE tasks
   SET status = 'claimed', claimed_by = $1, claimed_at = now(),
       lease_expires_at = now() + make_interval(secs => $2),
       attempts = attempts + 1, updated_at = now()
 WHERE id = (SELECT id FROM tasks
              WHERE queue = $3 AND status = 'pending' AND available_at <= now()
              ORDER BY priority DESC, available_at
              LIMIT 1
              FOR UPDATE SKIP LOCKED)
RETURNING id, payload, attempts, max_attempts;
```

What it does: the inner `SELECT` picks the best pending row that no other
transaction has locked; `SKIP LOCKED` skips locked rows instead of
waiting. The outer `UPDATE` marks it claimed in the same statement.
Expected result: one row, or zero rows when the queue is empty or all
pending rows are being claimed right now.

Tested behavior (two `psql` sessions): session A held `FOR UPDATE` on one
pending row; session B's `... FOR UPDATE SKIP LOCKED` returned a different
row immediately, while `... FOR UPDATE NOWAIT` failed with
`could not obtain lock on row in relation "tasks"`. In the Python demo, 4
workers processed 40 tasks: 40 distinct tasks, each exactly once.

Finish, fenced by lease holder, so a worker whose lease expired and was
reassigned cannot overwrite the new owner's result:

```sql
UPDATE tasks SET status = 'succeeded', claimed_by = NULL, lease_expires_at = NULL, updated_at = now()
 WHERE id = $1 AND claimed_by = $2;   -- 0 rows: lease was lost; discard your work
```

### Retries and dead letters

```sql
-- Failure: exponential backoff (illustrative: 30 s * 2^attempts), or dead letter
UPDATE tasks
   SET status = CASE WHEN attempts >= max_attempts THEN 'dead' ELSE 'pending' END,
       available_at = now() + interval '30 seconds' * power(2, attempts),
       claimed_by = NULL, claimed_at = NULL, lease_expires_at = NULL,
       last_error = $2, updated_at = now()
 WHERE id = $1 AND claimed_by = $3;
```

```sql
-- Reaper: requeue tasks whose worker died (lease expired). Run periodically.
UPDATE tasks
   SET status = CASE WHEN attempts >= max_attempts THEN 'dead' ELSE 'pending' END,
       claimed_by = NULL, claimed_at = NULL, lease_expires_at = NULL,
       last_error = 'lease expired', updated_at = now()
 WHERE status = 'claimed' AND lease_expires_at < now()
RETURNING id, status;
```

Tested: a claimed task with an expired lease went back to `pending`.
Alert on `dead` rows; a dead task needs a human or a fix, not a retry loop.

Semantics: delivery is **at least once**. A worker can finish the work and
crash before marking `succeeded`; the reaper then requeues it. Handlers
must be idempotent (use the tool-call idempotency key).

### Tradeoffs of PostgreSQL as the queue

- Advantage: enqueue in the same transaction as the business change (no dual-write problem), no extra infrastructure, SQL-visible state.
- Cost: every claim and finish is an `UPDATE`, producing dead tuples; heavy queues need aggressive autovacuum on `tasks` ([05-performance/vacuum.md](../05-performance/vacuum.md)) and periodic deletion of finished rows.
- Cost: `SKIP LOCKED` workers poll. Add `LISTEN/NOTIFY` as a wake-up hint (not as the source of truth: notifications are lost if nobody is listening).
- Cost: very high throughput or complex routing is better served by a broker.
- A worker holding a claim transaction open across the LLM call keeps a connection and row lock for the whole call; claim in a short transaction and rely on the lease, as above.

## Production usage

- Size leases above your p99 task duration with a margin (the 60 s in the demo is illustrative); long tasks renew: `UPDATE tasks SET lease_expires_at = now() + ... WHERE id = $1 AND claimed_by = $2`.
- Delete or archive finished tasks on a schedule in small batches; never one huge `DELETE`:

```sql
-- DESTRUCTIVE: permanently deletes rows. Confirm the predicate with a SELECT count(*) first,
-- run off-peak, keep batches small. Safer alternative: partition by time and drop partitions.
WITH old AS (
    SELECT id FROM tasks
    WHERE status IN ('succeeded', 'dead') AND updated_at < now() - interval '30 days'
    LIMIT 1000
    FOR UPDATE SKIP LOCKED
)
DELETE FROM tasks t USING old WHERE t.id = old.id;
```

(The 30 days is illustrative.) Dead rows may be worth keeping longer for diagnosis.

- Pooling: workers using transaction-mode poolers are fine with row locks and `xact` advisory locks. See [05-performance/connection-pooling.md](../05-performance/connection-pooling.md).

## Common mistakes

- Claiming with `SELECT ... FOR UPDATE` then `UPDATE` in separate transactions without `SKIP LOCKED`: workers queue up behind one row.
- No lease: a crashed worker's claim is stuck forever.
- Unfenced completion (`WHERE id = $1` only): a slow, expired worker overwrites a successful retry.
- Treating `SKIP LOCKED` as a consistent read: use it for queues only.
- Using only `ORDER BY priority`: starves low priority work; add aging or separate queues.

## Security considerations

- `payload` is untrusted if any part came from a model or user. Validate with the same schemas as tool arguments before enqueueing and before executing.
- `agent_app` cannot create tables or change `status` semantics beyond what the transition checks allow; a task payload must never carry SQL.

## Performance considerations

- `tasks_claim_idx` is partial on `status = 'pending'`: claim cost stays flat as finished rows accumulate. Verify with `EXPLAIN` that the claim uses it ([05-performance/explain.md](../05-performance/explain.md)).
- Lock contention shows as many workers on the same few rows; check `pg_stat_activity` / `pg_locks` ([14-observability/pg-locks.md](../14-observability/pg-locks.md)).

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Tasks stuck in `claimed` | Worker died, no reaper | Run the reaper; add `lease_expires_at` alert |
| Same task ran twice | At-least-once + non-idempotent handler | Idempotency key per side effect |
| Claim query slow | Index not used / bloat | `EXPLAIN`, `VACUUM (ANALYZE) tasks` |
| Workers idle while rows pending | `available_at` in future (backoff) or clock skew | Compare `available_at` to `now()` |

## Quick revision

- Claim = `UPDATE ... WHERE id = (SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1)`.
- Lease + reaper for crashes; fence completion on `claimed_by`.
- At-least-once: make handlers idempotent.
- Checkpoint `step` = next step; reuse stored decisions on resume.
