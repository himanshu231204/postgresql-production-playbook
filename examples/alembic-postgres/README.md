# Alembic + PostgreSQL Example

Runnable Alembic project: async `env.py` (asyncpg), SQLAlchemy 2.x models,
and seven migrations including a concurrent index and a zero-downtime
expand/contract rename. Tested with **PostgreSQL 16, Python 3.13,
Alembic 1.16.5, SQLAlchemy 2.0.43, asyncpg 0.30.0**. Explanations:
[09-alembic/](../../09-alembic/README.md).

## Layout

| Path | Purpose |
|---|---|
| `alembic.ini` | Config; contains no database URL |
| `alembic/env.py` | Async env; reads `MIGRATION_DATABASE_URL`; sets `lock_timeout`/`statement_timeout`; limits autogenerate to schema `app` |
| `app/models.py` | `User`, `Order` (`Mapped[...]`, `mapped_column()`, named constraints) |
| `alembic/versions/0001...0007` | See table below |
| `.env.example` | Placeholder variables |
| `requirements.txt` | Pinned dependencies |

| Revision | What | Lock / technique |
|---|---|---|
| 0001 | Create `users`, `orders` | New tables; nobody blocked |
| 0002 | `orders.currency` with constant default | Metadata-only on PG 11+; brief `ACCESS EXCLUSIVE` |
| 0003 | Index `orders(user_id, created_at)` | `CREATE INDEX CONCURRENTLY` in `autocommit_block()` |
| 0004 | **Expand**: add nullable `users.full_name` | Brief `ACCESS EXCLUSIVE` |
| 0005 | **Backfill** `name` -> `full_name` in batches | Autocommit batches; idempotent |
| 0006 | **Enforce** NOT NULL | `CHECK ... NOT VALID` -> `VALIDATE` -> `SET NOT NULL` |
| 0007 | **Contract**: drop `users.name` | Destructive; see docstring preconditions |

## Setup

Prerequisites: PostgreSQL 16 reachable, Python 3.11+.

**1. Create roles, database, schema** (once; as a superuser; **PostgreSQL SQL / psql**). Matches
[06-security/least-privilege.md](../../06-security/least-privilege.md); set
passwords per [passwords-and-secrets.md](../../06-security/passwords-and-secrets.md).

```sql
CREATE ROLE migration_owner LOGIN;
CREATE ROLE app_rw NOLOGIN;
CREATE ROLE app_api LOGIN;
GRANT app_rw TO app_api;
CREATE DATABASE appdb OWNER migration_owner;
\c appdb
CREATE SCHEMA app AUTHORIZATION migration_owner;
GRANT USAGE ON SCHEMA app TO app_rw;
ALTER DEFAULT PRIVILEGES FOR ROLE migration_owner IN SCHEMA app
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_rw;
ALTER DEFAULT PRIVILEGES FOR ROLE migration_owner IN SCHEMA app
    GRANT USAGE, SELECT ON SEQUENCES TO app_rw;
```

**2. Install and configure** (Unix shell; on Windows use
`py -m venv .venv` and `.venv\Scripts\activate`):

```bash
cd examples/alembic-postgres
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # edit placeholders; .env must stay uncommitted
set -a && source .env && set +a # exports MIGRATION_DATABASE_URL etc.
```

**3. Run**

```bash
alembic upgrade head     # expect: Running upgrade -> 0001 ... 0006 -> 0007
alembic current          # expect: 0007 (head)
alembic history
alembic check            # expect: No new upgrade operations detected.
alembic downgrade -1     # reverts 0007 (re-creates users.name from full_name)
alembic upgrade head
```

Stage the expand/contract flow like a real release:

```bash
alembic upgrade 0004     # expand; old app still works
# ... deploy app that writes name and full_name; insert some rows ...
alembic upgrade head     # backfill, enforce, contract (in production, contract is a later release)
```

Review SQL without a database change: `alembic upgrade 0004:head --sql`.

## Verified here

On PostgreSQL 16 against this project: `upgrade head`, `downgrade -1`,
`current`, `history`, `heads`, `check`, `upgrade ... --sql`, autogenerate
detecting an added column, `lock_timeout` aborting a migration that could
not get its lock (revision left unchanged), and the lock modes in
[production-migrations.md](../../09-alembic/production-migrations.md).
Not verified: very large tables, replicas, connection poolers.

## Notes

- Run as `migration_owner`; never give the application role these credentials.
- `alembic_version` lives in schema `app`; default privileges also grant
  `app_rw` access to it. Revoke if undesired.
- Do not edit applied revisions; add a new one
  ([rollback-strategies.md](../../09-alembic/rollback-strategies.md#editing-an-applied-migration)).
- `0007` is destructive and `downgrade` re-creates structure and copies
  from `full_name`. Do not run on a database you cannot recreate.
