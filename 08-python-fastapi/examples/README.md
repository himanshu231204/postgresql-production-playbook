# Examples

Runnable projects for this section. Both are tested against PostgreSQL 16
with the versions pinned in their `requirements.txt`.

| Project | Shows | Run |
|---|---|---|
| [fastapi-postgres](../../examples/fastapi-postgres/README.md) | FastAPI + async SQLAlchemy 2.x + asyncpg: lifespan, `Depends` session, repositories, health endpoints, TLS and PgBouncer settings, tests | `uvicorn app.main:app` |
| [sqlalchemy-postgres](../../examples/sqlalchemy-postgres/README.md) | Models, async and sync session factories, N+1 vs `selectinload` measured by statement count | `python demo_async.py` |

Both need the roles and schema from
[06-security/least-privilege.md](../../06-security/least-privilege.md);
the FastAPI example ships `sql/01_admin_setup.sql` and `sql/02_schema.sql`
that create them.

| Topic page | Example code |
|---|---|
| [sqlalchemy.md](../sqlalchemy.md) | `examples/sqlalchemy-postgres/models.py`, `demo_async.py` |
| [async-postgresql.md](../async-postgresql.md) | `examples/fastapi-postgres/app/main.py`, `app/db.py`, `app/routes.py` |
| [connection-pooling.md](../connection-pooling.md) | `examples/fastapi-postgres/app/db.py`, `.env.example` |
| [repository-pattern.md](../repository-pattern.md) | `examples/fastapi-postgres/app/repositories.py` |
