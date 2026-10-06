# SQLAlchemy 2.x + PostgreSQL Example

Standalone data-access example, no web framework: declarative models with
`Mapped`/`mapped_column`, async (asyncpg) and sync (psycopg 3) session
factories, a repository, and a demo that measures N+1 versus
`selectinload` by counting SQL statements. Tested with Python 3.13 against
PostgreSQL 16.

Pinned: SQLAlchemy 2.1.3, asyncpg 0.31.0, psycopg 3.3.6.

Explanations: [sqlalchemy.md](../../08-python-fastapi/sqlalchemy.md),
[repository-pattern.md](../../08-python-fastapi/repository-pattern.md).
The web layer is in [../fastapi-postgres/](../fastapi-postgres/README.md).

## Setup (Unix shell)

```bash
# Database: create roles and schema as in ../fastapi-postgres/sql/01_admin_setup.sql,
# then, as migration_owner:
psql -h localhost -U migration_owner -d appdb -f sql/schema.sql

python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

# Values come from .env.example; export them in your shell.
export DATABASE_URL='postgresql+asyncpg://app_api:PASSWORD@localhost:5432/appdb'
export SYNC_DATABASE_URL='postgresql+psycopg://app_api:PASSWORD@localhost:5432/appdb'

python demo_async.py
python demo_sync.py
```

Expected `demo_async.py` output (counts depend only on the page size, 5):

```
lazy load blocked: InvalidRequestError
N+1 style: 6 statements
selectinload: 2 statements, ... orders
customers after rollback: ...
```

The demo inserts sample rows and rolls them back; it leaves no data.

## Files

| File | Purpose |
|---|---|
| `models.py` | `Customer`, `Order`; relationships use `lazy="raise"` |
| `session.py` | Engine and sessionmaker factories with explicit pool and timeout settings |
| `repository.py` | `CustomerRepository` over `AsyncSession` (flush, no commit) |
| `demo_async.py` | N+1 vs `selectinload`, transaction rollback |
| `demo_sync.py` | Same stack with a blocking `Session` and `sessionmaker.begin()` |
| `sql/schema.sql` | Tables and the index each query needs |

## Notes

- The database encoding must be UTF8. On a `SQL_ASCII` database, psycopg
  returns `bytes` for text and SQLAlchemy cannot initialize the sync
  engine.
- The app role needs only DML; DDL runs as `migration_owner`
  ([least-privilege.md](../../06-security/least-privilege.md)).
