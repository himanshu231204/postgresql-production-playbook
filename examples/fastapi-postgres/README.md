# FastAPI + PostgreSQL Example

Production-shaped async service: FastAPI, SQLAlchemy 2.x `AsyncSession`,
asyncpg, pydantic-settings, repository layer, health endpoints, and a
least-privilege database role. Tested with Python 3.13 against PostgreSQL 16.

Pinned in `requirements.txt`: FastAPI 0.142.2, SQLAlchemy 2.1.3, asyncpg
0.31.0, Pydantic 2.13.5, pydantic-settings 2.15.0, uvicorn 0.54.0. Needs
Python 3.11 or later (`TimeoutError` handling in `app/routes.py`).

Explanations: [08-python-fastapi/](../../08-python-fastapi/README.md).

## Layout

| Path | Purpose |
|---|---|
| `app/config.py` | Settings from environment variables; `DATABASE_URL` has no default |
| `app/db.py` | Engine (pool, timeouts, TLS, PgBouncer options) and `async_sessionmaker` |
| `app/main.py` | `lifespan`: create engine at startup, `dispose()` at shutdown |
| `app/deps.py` | `SessionDep = Annotated[AsyncSession, Depends(get_session)]` |
| `app/repositories.py` | All SQL; flushes, never commits |
| `app/routes.py` | Handlers own the transaction (`commit()`); health endpoints |
| `sql/01_admin_setup.sql` | Roles, database, schema, grants (admin; mirrors [least-privilege.md](../../06-security/least-privilege.md)) |
| `sql/02_schema.sql` | Tables (run as `migration_owner`; use Alembic in a real project) |
| `tests/` | API tests against a real PostgreSQL |

## Setup (Unix shell)

```bash
# 1. Database: roles, schema, tables. Set passwords interactively.
psql -h localhost -U dba_admin -d postgres -f sql/01_admin_setup.sql
psql -h localhost -U dba_admin -d postgres -c '\password app_api'
psql -h localhost -U dba_admin -d postgres -c '\password migration_owner'
psql -h localhost -U migration_owner -d appdb -f sql/02_schema.sql

# 2. Python environment (keep the venv outside version control)
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt

# 3. Configuration
cp .env.example .env        # then edit DATABASE_URL; .env is git-ignored

# 4. Run
uvicorn app.main:app --port 8000
```

`sql/01_admin_setup.sql` contains `CREATE DATABASE` and a psql
`\connect`; run it with `psql -f`, not through another client.

## Try it

```bash
curl -s localhost:8000/health/ready
curl -s -X POST localhost:8000/customers -H 'content-type: application/json' \
  -d '{"email":"ada@example.test","name":"Ada"}'
curl -s -X POST localhost:8000/customers/1/orders -H 'content-type: application/json' \
  -d '{"total_cents":2500}'
curl -s 'localhost:8000/customers/with-orders?limit=10'   # selectinload: 2 queries
```

| Endpoint | Behavior |
|---|---|
| `GET /health/live` | Process liveness; no database access |
| `GET /health/ready` | `SELECT 1` bounded to 2 s; `503` when the database is unreachable |
| `POST /customers` | `201`; `409` on duplicate email (unique constraint, SQLSTATE `23505`) |
| `GET /customers?limit&after_id` | Keyset pagination |
| `GET /customers/with-orders` | `selectinload`: 2 statements regardless of page size |
| `POST /customers/{id}/orders` | `201`; `404` when the customer is missing (FK violation, `23503`) |

## Tests

```bash
export DATABASE_URL=postgresql+asyncpg://app_api:PASSWORD@localhost:5432/appdb
pytest -q
```

Tests write rows into the configured database with random emails; point
them at a development database, never production. Without `DATABASE_URL`
they skip.

## Configuration

See `.env.example`. Notable settings:

| Variable | Effect |
|---|---|
| `DB_POOL_SIZE`, `DB_MAX_OVERFLOW` | Per-process pool; worst case per host = workers x (sum) |
| `DB_POOL_TIMEOUT` | Seconds a request waits for a pooled connection before an error |
| `DB_STATEMENT_TIMEOUT_MS` | Sent as the `statement_timeout` startup parameter |
| `DB_SSL_CA_FILE` | Enables certificate and host-name verification |
| `DB_USE_NULL_POOL`, `DB_DISABLE_STATEMENT_CACHE` | PgBouncer transaction mode without prepared-statement tracking; see [connection-pooling.md](../../08-python-fastapi/connection-pooling.md) |

## Known limitations

- No authentication or rate limiting; this is a database-access example.
- Schema is plain SQL. Migrations belong in Alembic
  ([09-alembic/](../../09-alembic/README.md)).
- Starlette's `TestClient` emits a deprecation warning about `httpx`
  with the pinned versions; tests still pass.
- Not exercised against PgBouncer.
