# Audit Logs

## What it is

An append-only record of who or what changed which entity, when, and how,
plus the usage ledger (`model_usage`) and evaluation records
(`evaluation_runs`) that make agent behavior accountable. Tables:
`audit_logs`, `model_usage`, `evaluation_runs`.

## Why it matters

When an agent closes the wrong ticket or a bill spikes, the questions are
"which run, which tool call, under whose authority, with what arguments,
at what cost". If the runtime role can edit or delete audit rows, the
record is only as trustworthy as the least careful code path or the most
successful prompt injection.

## Append-only `audit_logs`

Schema (`010_schema.sql`): `id` (identity), `occurred_at timestamptz`,
`actor_type IN ('user','agent','system')`, `actor_id`, `action`,
`entity_type`, `entity_id` (text), `details jsonb`. No foreign keys, so
rows outlive the entities they describe.

### Layer 1: privileges (primary control)

```sql
-- PostgreSQL SQL (030_grants.sql)
GRANT SELECT, INSERT ON audit_logs TO agent_rw;
REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs FROM agent_rw;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA agent TO agent_rw;   -- identity column
```

Tested as `agent_app`: `INSERT` succeeded; `DELETE`, `UPDATE`, and
`TRUNCATE` each failed with `permission denied for table audit_logs`.
Verify with `SELECT has_table_privilege('agent_app', 'agent.audit_logs', 'UPDATE');` (returned `false`).

### Layer 2: trigger (defense in depth)

`040_audit.sql` raises on `UPDATE`, `DELETE`, and `TRUNCATE`:

```sql
CREATE TRIGGER audit_logs_no_update_delete
    BEFORE UPDATE OR DELETE ON audit_logs
    FOR EACH ROW EXECUTE FUNCTION audit_logs_immutable();
CREATE TRIGGER audit_logs_no_truncate
    BEFORE TRUNCATE ON audit_logs
    FOR EACH STATEMENT EXECUTE FUNCTION audit_logs_immutable();
```

Tested as `agent_owner` (who has the privileges): both attempts failed with
`audit_logs is append-only (DELETE not allowed)` / `(UPDATE not allowed)`.

What this does not stop: a superuser or the table owner can drop the
trigger or disable it (`ALTER TABLE ... DISABLE TRIGGER`). For a stronger
guarantee, ship audit rows to storage the database admins cannot modify
(object-lock bucket, a separate logging system), restrict who has the
owner/superuser role, and monitor DDL on the table. A hash chain (each
row stores a hash of the previous) detects tampering after the fact; it
is not implemented in the example.

### Automatic audit of status changes

`audit_status_change()` is an `AFTER INSERT OR UPDATE` trigger on
`agent_runs` and `tool_calls`. It writes a row in the **same transaction**
as the change, so there is no committed state change without an audit row,
and no audit row for a rolled-back change.

Actor attribution: the application sets a transaction-local setting, and
the trigger falls back to the database role:

```sql
BEGIN;
SELECT set_config('agent.actor', 'worker:w1', true);   -- true = local to this transaction
UPDATE agent_runs SET status = 'running', version = version + 1 WHERE id = $1;
COMMIT;
-- audit_logs: actor_id = 'worker:w1', action = 'agent_runs.status_changed',
--             details = {"from": "queued", "to": "running"}
```

`agent.actor` is a convention set by application code, not
authentication: any code that can run SQL as the role can set it to
anything. Treat it as attribution; the security boundary is who can
connect and with what grants. Use `session_user` (the login role) for
per-service identity.

Tradeoff of triggers: automatic and impossible to forget, versus a hidden
write on every status update (extra insert and index maintenance on the
busiest table) and logic that lives outside application code. Business
events with meaning (a ticket closed, a refund issued) are better written
explicitly by the application in the same transaction, as in
[transactional_write.py](../examples/production-agent-db/demo/transactional_write.py)
(`ticket.closed`).

### What to log

| Log | Do not log |
|---|---|
| Status transitions, tool executions (tool, run, key), approvals, permission denials | Secrets, API keys, full prompts by default |
| Rejected tool calls (validation failures, unauthorized ids) with the reason | Raw PII unless required and retention-controlled |
| Who/what acted (`actor_type`, `actor_id`) | Unbounded payloads (store references/ids; cap `details` size) |

### Querying

```sql
-- History of one run (uses audit_logs_entity_idx)
SELECT occurred_at, actor_id, action, details
FROM audit_logs
WHERE entity_type = 'agent_runs' AND entity_id = $1
ORDER BY occurred_at, id;

-- Activity in a window (BRIN index on occurred_at helps on large, time-ordered tables)
SELECT action, count(*) FROM audit_logs
WHERE occurred_at >= now() - interval '1 hour'
GROUP BY action ORDER BY count(*) DESC;
```

Both tested. Index tradeoffs: the `(entity_type, entity_id, occurred_at)`
B-tree serves entity history but adds write cost to every audit insert;
the BRIN index is tiny and only effective while physical order tracks
time (appends only; true here because rows are never updated or moved).

### Growth and retention

Audit data grows forever by design. Options: time partitioning with
archive-then-detach (same mechanics and caveats as
[conversation-memory.md](conversation-memory.md#partitioned-messages)),
or export to cold storage. Dropping audit partitions is destructive and
needs a role that is not `agent_app`; define the retention period with
your compliance requirements, not as a technical default.

## `model_usage`: tokens and cost

One row per model call: `run_id`, `provider`, `model`, `input_tokens`,
`output_tokens`, `cost_usd numeric(12,6)`, `latency_ms`. The runtime role
has `SELECT, INSERT` only: a ledger is corrected by adding a compensating
row, not editing history.

```sql
INSERT INTO model_usage (run_id, provider, model, input_tokens, output_tokens, cost_usd, latency_ms)
VALUES ($1, $2, $3, $4, $5, $6, $7);
```

```sql
-- Spend per day and model
SELECT date_trunc('day', created_at) AS day, model,
       sum(input_tokens) AS in_tok, sum(output_tokens) AS out_tok, sum(cost_usd) AS cost_usd
FROM model_usage
WHERE created_at >= now() - interval '30 days'
GROUP BY 1, 2 ORDER BY 1 DESC, 5 DESC;

-- Most expensive runs
SELECT r.id, sum(u.cost_usd) AS run_cost
FROM agent_runs r JOIN model_usage u ON u.run_id = r.id
GROUP BY r.id ORDER BY run_cost DESC LIMIT 10;
```

Both tested against a stub row.

Design notes:

- Store `cost_usd` computed at call time from the price in force then. Prices change; recomputing history from a current price table gives wrong totals. The alternative (a `model_prices` table with validity ranges and a join) keeps raw tokens as the source of truth and allows re-pricing, at the cost of a more complex query and a lookup at write or report time.
- Token counts come from the provider's response; treat them as authoritative over local estimates. Cached/reasoning/tool token categories differ by provider: add columns for the ones your provider bills separately rather than folding them into two numbers.
- Per-user budgets: aggregate by joining `agent_runs` -> `conversations` -> `users`; enforce limits in the application before the call (a database `CHECK` cannot see aggregates). Checking then inserting is racy under concurrency; reserve budget in a row you lock (`FOR UPDATE`) if overshoot matters.
- High call volume makes `model_usage` large; partition by time or roll up daily and archive raw rows.

## `evaluation_runs`

One row per evaluation of an `agent_version` against a `dataset`:
`status`, `metrics jsonb` (object), `started_at`, `finished_at`. Compare
versions to catch regressions:

```sql
SELECT agent_version, started_at::date AS day, metrics->>'pass_rate' AS pass_rate
FROM evaluation_runs
WHERE dataset = $1 AND status = 'succeeded'
ORDER BY started_at DESC;
```

Tested with a sample row. Keep per-case results in a separate table you
add if you need to query them; one JSONB blob of thousands of cases is
hard to analyze and update. Evaluation runs are not production data:
run them against synthetic or sanitized data and a separate database or
schema when they can write.

## Security considerations

- The audit table is the one place the agent role must never have `UPDATE`/`DELETE`.
- Audit rows may contain identifiers and reasons that are themselves sensitive: restrict `SELECT` (the read-only role in the example has none).
- `details` is JSONB built by code: use `jsonb_build_object` or bound parameters, never string concatenation.
- Alert on rejected tool calls and permission errors; they are the visible trace of an injection attempt.

## Common mistakes

- Giving the application role `UPDATE` on audit "for corrections".
- Writing audit rows in a separate transaction (committed audit for a rolled-back action, or the reverse).
- Foreign keys from `audit_logs` with `ON DELETE CASCADE`: deleting an entity erases its history.
- Editing `model_usage` rows instead of adding corrections.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `permission denied for table audit_logs` on insert | Missing `INSERT` or sequence `USAGE` | Re-run `030_grants.sql`; check `\dp audit_logs` |
| `audit_logs is append-only` | Something tried `UPDATE`/`DELETE` | Fix the code; never drop the trigger to "make it work" |
| Audit actor is the DB role, not the worker | `agent.actor` not set in that transaction | Set it with `set_config(..., true)` at transaction start |
| Audit table slow to insert | Too many indexes / bloat from nothing (append only) | Drop unused indexes; check `pg_stat_user_indexes` |

## Quick revision

- `REVOKE UPDATE, DELETE, TRUNCATE`; add a trigger as backup; ship logs off-box for real immutability.
- Audit in the same transaction as the change.
- Ledger tables are corrected by new rows.
- Prices change: store cost at call time.
