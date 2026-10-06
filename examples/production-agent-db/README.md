# Production Agent DB (example)

Runnable companion to [11-agentic-ai/](../../11-agentic-ai/README.md): the
full agent schema (users, conversations, messages, agent_runs, tool_calls,
workflow_state, tasks, audit_logs, model_usage, evaluation_runs) as SQL
files, plus four small Python demos for the patterns that matter in
production. No LLM API key and no network access: the model and tools are
stubs ([demo/tools.py](demo/tools.py)).

Versions: PostgreSQL 16, Python 3.11+ (tested with 3.13), psycopg 3.3.6,
Pydantic 2.13.5. No PostgreSQL extensions required.

## Layout

| Path | Purpose |
|---|---|
| `sql/000_roles.sql` | Roles (`agent_owner`, `agent_rw`, `agent_app`, `agent_ro`) and database |
| `sql/010_schema.sql` | Ten tables, constraints, indexes |
| `sql/020_business_example.sql` | Example business table (`support_tickets`) |
| `sql/030_grants.sql` | Least-privilege grants, append-only audit privileges |
| `sql/040_audit.sql` | Audit immutability and status-change triggers |
| `sql/050_state_machine.sql` | Legal `agent_runs` status transitions |
| `demo/idempotent_tool_call.py` | `UNIQUE (run_id, idempotency_key)` + `ON CONFLICT DO NOTHING`, two racing workers |
| `demo/task_claiming.py` | `FOR UPDATE SKIP LOCKED` with 4 workers, leases, reaper |
| `demo/optimistic_concurrency.py` | `version` column, stale write rejected and retried |
| `demo/transactional_write.py` | Agent state + business data in one transaction; rollback; hostile model output rejected |
| `.env.example` | Placeholder configuration |
| `requirements.txt` | Pinned Python dependencies |

## Setup

**Unix shell** (macOS/Linux). Requires a running PostgreSQL 16 server and
a superuser (or equivalent) connection for step 1.

```bash
# 1. Roles and database (superuser). Then set passwords out of band (never commit them).
psql "$ADMIN_DATABASE_URL" -v ON_ERROR_STOP=1 -f sql/000_roles.sql
psql "$ADMIN_DATABASE_URL" -c "ALTER ROLE agent_owner PASSWORD 'CHANGE_ME_OWNER'" \
                           -c "ALTER ROLE agent_app   PASSWORD 'CHANGE_ME_APP'"
# (use \password in psql so the value does not land in shell history)

# 2. Schema, as the owner role
export OWNER_DATABASE_URL=postgresql://agent_owner:PASSWORD@localhost:5432/agentdb
for f in 010_schema 020_business_example 030_grants 040_audit 050_state_machine; do
  psql "$OWNER_DATABASE_URL" -v ON_ERROR_STOP=1 -f "sql/$f.sql"
done

# 3. Python environment (keep the venv outside the repo or git-ignored)
python3 -m venv ~/.venvs/agent-db && source ~/.venvs/agent-db/bin/activate
pip install -r requirements.txt

# 4. Configure and run the demos as the runtime role (agent_app)
cp .env.example .env            # edit DATABASE_URL; .env is git-ignored
set -a; source .env; set +a
cd demo
python idempotent_tool_call.py
python task_claiming.py
python optimistic_concurrency.py
python transactional_write.py
```

Windows (PowerShell): set `$env:DATABASE_URL = "postgresql://agent_app:PASSWORD@localhost:5432/agentdb"`, create the venv with `py -m venv .venv` and activate with `.\.venv\Scripts\Activate.ps1`; the `psql` and `python` commands are otherwise the same.

`000_roles.sql` creates cluster-wide roles and a database; on managed
PostgreSQL you may need to create these through the provider and adapt
names. The demos write rows (users, runs, tickets, tasks) into the
database: run them against a local or disposable database, not production.

## Expected output (abridged, from a test run)

```text
idempotent_tool_call.py   outcomes: [False, True] / side effects executed: 1 / OK: exactly-once execution
task_claiming.py          tasks processed: 40 | distinct: 40 / OK: expired lease requeued
optimistic_concurrency.py worker B rejected: version 0 is stale / final state ... version 2 / OK: no lost update
transactional_write.py    hostile output rejected / after rollback: ('open', 0) / after retry + replay: ('closed', 1)
```

Per-worker task counts in `task_claiming.py` vary between runs.

## What each demo shows

- **Idempotency**: two threads execute the same logical call; the unique index serialises them, one runs the side effect, the other returns the stored result.
- **SKIP LOCKED**: workers never wait on each other's locked rows; each task is processed once; a crashed worker's expired lease is requeued by the reaper.
- **Optimistic concurrency**: `UPDATE ... WHERE version = $n` returns zero rows for the stale writer, which reloads and retries.
- **Transactional consistency**: ticket update, tool-call result, checkpoint, and audit row commit together or not at all. Validation rejects model output with unknown fields before any SQL runs; the injection string in `resolution` is never interpolated into SQL.

## Verify the privilege model

```sql
-- As a superuser, in agentdb
SELECT has_table_privilege('agent_app', 'agent.audit_logs', 'UPDATE') AS can_update_audit,   -- false
       has_table_privilege('agent_app', 'agent.audit_logs', 'INSERT') AS can_insert_audit;   -- true
SELECT has_schema_privilege('agent_app', 'agent', 'CREATE') AS can_create;                    -- false
```

## Limitations

- Stubs only: no real model, no real external side effects. The idempotency demo's "external effect" is an in-process list; real external calls need downstream idempotency or an outbox ([tool-calls.md](../../11-agentic-ai/tool-calls.md#limits-of-the-guard)).
- pgvector memory is described in [conversation-memory.md](../../11-agentic-ai/conversation-memory.md#vector-memory-with-pgvector) but not part of the DDL here; see [10-pgvector/](../../10-pgvector/README.md) and [examples/pgvector-rag](../pgvector-rag/README.md).
- Single database, no migration tool: apply files in order. In production run them through your migration workflow ([09-alembic/](../../09-alembic/README.md)).
- Demos use one connection per thread and no pool; see [05-performance/connection-pooling.md](../../05-performance/connection-pooling.md).
