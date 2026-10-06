# Writing Migrations

Alembic 1.16, SQLAlchemy 2.0, PostgreSQL 16. The complete, tested code
lives in [examples/alembic-postgres/](../examples/alembic-postgres/README.md).

## What it is

A migration is a Python file with `revision`, `down_revision`,
`upgrade()` and `downgrade()`. Revisions form a linked list (a DAG if
branched); `alembic_version` stores the current revision id.

## Why it matters

Schema changes are the riskiest routine production operation: they take
locks, can rewrite tables, and must stay compatible with the application
version that is running while they execute. See
[production-migrations.md](production-migrations.md).

## Setup

```bash
pip install "alembic==1.16.5" "SQLAlchemy==2.0.43" "asyncpg==0.30.0"
alembic init -t async alembic     # async env.py; use plain `alembic init alembic` for a sync driver
```

Do not put the URL in `alembic.ini` (it is committed). Read it from the
environment in `env.py`.

## `env.py` pattern (async, URL from env, guard rails)

Excerpt from the example's
[env.py](../examples/alembic-postgres/alembic/env.py). **Python**:

```python
import asyncio, os
from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine
from app.models import SCHEMA, Base

target_metadata = Base.metadata

def get_url() -> str:
    url = os.environ.get("MIGRATION_DATABASE_URL")
    if not url:
        raise RuntimeError("MIGRATION_DATABASE_URL is not set")
    return url

async def run_async_migrations() -> None:
    connectable = create_async_engine(
        get_url(),
        poolclass=pool.NullPool,
        connect_args={"server_settings": {          # asyncpg startup parameters (milliseconds)
            "lock_timeout": os.environ.get("MIGRATION_LOCK_TIMEOUT_MS", "5000"),
            "statement_timeout": os.environ.get("MIGRATION_STATEMENT_TIMEOUT_MS", "300000"),
            "application_name": "alembic",
        }},
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)   # do_run_migrations calls context.configure(connection=...)
    await connectable.dispose()
```

Choices that matter:

| Setting | Why |
|---|---|
| `MIGRATION_DATABASE_URL` (separate from the app's `DATABASE_URL`) | Migrations connect as `migration_owner`; the app never holds DDL credentials |
| `server_settings` `lock_timeout` | A DDL that cannot get its lock fails fast instead of queueing and blocking every later query on the table (see [lock queueing](production-migrations.md#lock-queueing-and-lock_timeout)). Session-level, so it survives the `COMMIT` inside `autocommit_block()`; a `SET LOCAL` would not |
| `server_settings` `statement_timeout` | Bounds a runaway statement. 300000 ms is an illustrative default, not a rule; raise it for large index builds |
| `NullPool` | One short-lived connection; nothing left holding locks |
| `version_table_schema` | Keeps `alembic_version` in the app schema, not `public` |
| `include_schemas=True` + `include_name` | Autogenerate compares only the schema(s) you own |
| `compare_type=True`, `compare_server_default=True` | Detect column type drift (default on since 1.12; explicit for clarity) and server-default drift (off by default) |
| Named constraints (`MetaData(naming_convention=...)`) | Constraints get stable names so later migrations can `DROP`/`VALIDATE` them. Unnamed constraints get server-generated names |

If you use `pgbouncer` in transaction mode, run migrations on a **direct**
connection: session-level settings and advisory locks do not survive
transaction pooling (see [05-performance/connection-pooling.md](../05-performance/connection-pooling.md)).

## Model style

SQLAlchemy 2.x only: `DeclarativeBase`, `Mapped[...]`, `mapped_column()`.
See [models.py](../examples/alembic-postgres/app/models.py) and
[08-python-fastapi/sqlalchemy.md](../08-python-fastapi/sqlalchemy.md).

## Autogenerate and what it does not detect

```bash
alembic revision --autogenerate -m "add orders note" --rev-id 0008
```

Autogenerate compares `target_metadata` to the live database and writes
`op.*` calls. It is a draft. Per the Alembic documentation it does
**not** reliably detect:

| Not detected / unreliable | What to do |
|---|---|
| Table or column **renames** (seen as drop + add) | Write the rename by hand, or use [expand/contract](production-migrations.md#expandcontract-rename-a-column) |
| Changes to `CHECK` constraints and some other anonymous constraints | Hand-write `op.create_check_constraint` / `op.execute` |
| Changes to sequences, identity details, and many PostgreSQL-specific objects (enums values, views, functions, triggers, extensions, grants, row-level security, partition definitions) | Hand-write with `op.execute(...)` |
| Column type changes if `compare_type` is disabled (default is on since Alembic 1.12) | Keep it `True` in `env.py` |
| Server default changes unless `compare_server_default=True` | Enable it |
| Anything outside the included schemas/`MetaData` | Not tracked |

It also emits **unsafe-for-production** forms: `CREATE INDEX` without
`CONCURRENTLY`, `ALTER COLUMN ... SET NOT NULL` with a full scan,
`ADD CONSTRAINT` without `NOT VALID`, `DROP COLUMN`. Rewrite those by
hand (below).

Verified while writing the example: after the migrations were applied,
`alembic check` reported drift (`Identity` on the primary keys had been
omitted from the models); fixing the model made it print
`No new upgrade operations detected.` Run `alembic check` in CI.

## Transactional DDL

PostgreSQL DDL is transactional, so by default a whole
`alembic upgrade` runs in one transaction: if revision 5 of 7 fails,
nothing is applied and `alembic_version` is unchanged. Alembic logs
`Will assume transactional DDL.` Two consequences:

- Locks taken by early revisions are held until the whole run commits.
  Use `transaction_per_migration=True` in `context.configure(...)` to
  commit after each revision when you run several at once.
- Statements that cannot run in a transaction need
  `autocommit_block()`.

## Statements that cannot run in a transaction

`CREATE INDEX CONCURRENTLY`, `DROP INDEX CONCURRENTLY`,
`REINDEX ... CONCURRENTLY`, `ALTER TYPE ... ADD VALUE` (before PG 12), and
`VACUUM` fail inside a transaction block
(`CREATE INDEX CONCURRENTLY cannot run inside a transaction block`,
reproduced on PG 16). **Python**:

```python
def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_orders_user_id_created_at", "orders", ["user_id", "created_at"],
            schema="app", postgresql_concurrently=True,
        )

def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index("ix_orders_user_id_created_at", table_name="orders",
                      schema="app", postgresql_concurrently=True)
```

`autocommit_block()` commits the migration transaction so far, runs the
block in autocommit, then starts a new transaction. It is verified here
with the asyncpg driver. Cautions:

- Work done before the block is **committed**, so the revision is no
  longer atomic. Put the concurrent statement in its **own revision**.
- A failed `CREATE INDEX CONCURRENTLY` leaves an `INVALID` index.
  Find it (`SELECT indexrelid::regclass FROM pg_index WHERE NOT indisvalid;`),
  `DROP INDEX CONCURRENTLY` it, and re-run. See
  [03-database-design/indexes.md](../03-database-design/indexes.md#building-an-index-without-blocking-writes).
- Index justification belongs in the docstring: the query it serves and
  the write/storage cost (AGENTS.md section 8).

## Data migrations

- Use `op.execute(sa.text(...))` with bound parameters; never f-string
  user or LLM-derived input into SQL.
- Do not import application models into migrations: models change, the
  migration must not. Use SQL or a minimal `sa.table()` stub.
- Large updates: batch with commits per batch. See
  [production-migrations.md](production-migrations.md#batched-backfill).

## Common mistakes

- Trusting autogenerate output without reading it.
- Editing an already-applied migration instead of adding a new one.
- Two developers each creating a head: `alembic upgrade head` fails with
  multiple heads. Run `alembic heads` in CI; fix with `alembic merge`.
- Running migrations as a superuser: new objects get the wrong owner
  and miss default privileges
  ([least-privilege.md](../06-security/least-privilege.md#common-mistakes)).
- Running `upgrade head` automatically on every app instance start:
  concurrent runners, wrong role, no review. Run it once from the
  pipeline.
- Putting the real DB URL in `alembic.ini`.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `Multiple head revisions are present` | Two branches. `alembic heads`, then `alembic merge -m "merge" <h1> <h2>` |
| `Can't locate revision identified by 'x'` | DB stamped with a revision missing from the repo (wrong branch/deploy). `alembic current`, `alembic history` |
| `canceling statement due to lock timeout` | `lock_timeout` fired; a long transaction holds a conflicting lock. See [lock-contention runbook](../15-production-runbooks/lock-contention.md); retry |
| Autogenerate wants to drop tables you did not model | Other schemas/tables in the database; restrict with `include_schemas` / `include_name` / `include_object` |
| `permission denied for schema` | Connected as the wrong role |
| Migration half-applied | See [rollback-strategies.md](rollback-strategies.md#a-migration-failed-mid-way) and [15-production-runbooks/failed-migration.md](../15-production-runbooks/failed-migration.md) |

## Quick revision

- URL from env, DDL role, `lock_timeout` on the session.
- Autogenerate is a draft; `alembic check` in CI.
- `CONCURRENTLY` needs `autocommit_block()`, in its own revision.
- Transactional DDL: a failed `upgrade` rolls back unless you committed
  in an `autocommit_block()`.
