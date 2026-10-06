# Async PostgreSQL: asyncpg, AsyncSession, FastAPI

Versions: SQLAlchemy 2.1.3, asyncpg 0.31.0, FastAPI 0.142.2, Python 3.13
(3.11 or later required by the example). Code:
[examples/fastapi-postgres/](../examples/fastapi-postgres/README.md).

## What it is

asyncpg is an asyncio-native PostgreSQL driver. SQLAlchemy's
`postgresql+asyncpg://` dialect wraps it so `AsyncEngine` and
`AsyncSession` run on the event loop. FastAPI runs `async def` handlers
on that loop.

## Why it matters

An `async def` handler that makes a blocking call (a sync driver, a slow
CPU loop) stalls every other request in that worker. An async stack
removes that failure mode for I/O, but adds its own rules: no implicit
lazy loading, no sharing a session between tasks, and driver-specific
configuration (TLS, prepared statements).

## Sync vs async

Both are production-viable; neither is universally better.

| Concern | Async (`AsyncSession`, asyncpg) | Sync (`Session`, psycopg 3, `def` handlers) |
|---|---|---|
| Concurrency model | Many requests share one event loop while awaiting I/O | FastAPI runs `def` handlers in a thread pool; concurrency bounded by threads |
| Fits when | I/O-bound services, many concurrent slow-ish requests, other async I/O (HTTP, LLM calls, websockets) | Simple services, CPU-heavy handlers, libraries that are sync-only, teams who want ordinary stack traces and debugging |
| Pitfalls | Blocking call inside `async def` freezes the loop; lazy loads raise `MissingGreenlet`; one session per task | Thread pool exhaustion under slow queries; pool size must cover thread count |
| Dependency surface | asyncpg, `greenlet` (installed via `sqlalchemy[asyncio]`) | psycopg 3 (or psycopg2) |
| ORM behavior | Explicit loaders required; `await` on every DB call | Lazy loading works (still prefer explicit loaders) |
| Pool arithmetic | Same: `processes x (pool_size + max_overflow)` | Same, and also at most one connection per active thread |

Do not mix: a sync `Session` call inside an `async def` handler blocks the
loop; an `async def` handler awaiting nothing gains nothing. If part of a
codebase is sync (scripts, Alembic), give it its own sync engine and URL
(`postgresql+psycopg://`); the SQLAlchemy example does this
(`examples/sqlalchemy-postgres/demo_sync.py`).

## Syntax

### URL

```text
postgresql+asyncpg://app_api:PASSWORD@db.internal:5432/appdb
```

Read it from an environment variable; never hardcode it
([06-security/passwords-and-secrets.md](../06-security/passwords-and-secrets.md)).
Percent-encode special characters in the password or build the URL with
`sqlalchemy.engine.URL.create(...)`.

### Lifespan: one engine per process

```python
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.db import build_engine, build_sessionmaker


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    engine = build_engine(get_settings())
    app.state.engine = engine
    app.state.sessionmaker = build_sessionmaker(engine)
    try:
        yield
    finally:
        await engine.dispose()


app = FastAPI(lifespan=lifespan)
```

Use `lifespan`, not the deprecated `@app.on_event("startup")`.

### Session dependency

```python
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    sessionmaker: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    async with sessionmaker() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]
```

One session per request; closing it returns the connection and rolls
back anything uncommitted. The handler commits explicitly (see
[sqlalchemy.md](sqlalchemy.md#transactions)); committing in the
dependency's teardown would depend on when FastAPI runs that code
relative to sending the response.

### Concurrency inside a request

An `AsyncSession` is not safe for concurrent use. Do not pass one session
to `asyncio.gather()` tasks. For parallel queries, open one session per
task (each holds its own pooled connection), and size the pool for it.

## TLS with asyncpg

asyncpg does not accept libpq's `sslmode`/`sslrootcert` as keyword
arguments. Verified against SQLAlchemy 2.1.3 and asyncpg 0.31.0 on
PostgreSQL 16 with a self-signed server certificate:

| Configuration | Result |
|---|---|
| (no setting) | asyncpg default is `prefer`: TLS if the server offers it, silent plaintext fallback otherwise. Not acceptable for production |
| `?ssl=require` | TLS, certificate **not** verified |
| `?ssl=verify-full` | Verifies certificate and host name against the CA in `~/.postgresql/root.crt`; fails with a missing-file error if absent. There is no URL parameter for a different CA path |
| `?sslmode=require` | `TypeError: connect() got an unexpected keyword argument 'sslmode'` |
| `?ssl=verify-full&sslrootcert=/path/ca.pem` | `TypeError: ... unexpected keyword argument 'sslrootcert'` |
| `connect_args={"ssl": ssl.create_default_context(cafile="/path/ca.pem")}` | TLS with certificate and host-name verification (`verify-full` semantics); `pg_stat_ssl.ssl` was `t` |
| Same context, CA that did not sign the server certificate | `SSLCertVerificationError: CERTIFICATE_VERIFY_FAILED`, connection refused |

Production configuration:

```python
import ssl

from sqlalchemy.ext.asyncio import create_async_engine

ssl_context = ssl.create_default_context(cafile="/etc/ssl/certs/db-ca.pem")
# create_default_context(): verify_mode=CERT_REQUIRED, check_hostname=True

engine = create_async_engine(
    DATABASE_URL,                       # no ssl parameter in the URL
    connect_args={"ssl": ssl_context},
)
```

- The host in the URL must match a name in the certificate's SAN.
- asyncpg ignores `ssl` for Unix domain sockets.
- To also require the server to demand TLS, add `hostssl` /
  `hostnossl ... reject` lines in `pg_hba.conf`
  ([06-security/ssl.md](../06-security/ssl.md)).
- Confirm from the server side:
  `SELECT ssl, version FROM pg_stat_ssl WHERE pid = pg_backend_pid();`.
- Synchronous psycopg 3 uses libpq, where `?sslmode=verify-full&sslrootcert=/path/ca.pem`
  is the standard form (not exercised in this repository's validation).
- The example app enables this with `DB_SSL_CA_FILE=/path/ca.pem`.

## Timeouts

| Layer | Setting |
|---|---|
| Wait for a pooled connection | `pool_timeout` |
| TCP/TLS connect | `connect_args={"timeout": seconds}` |
| Per-operation client limit | `connect_args={"command_timeout": seconds}` |
| Server cancels long statements | `statement_timeout` (role-level or startup parameter) |
| Server kills stuck transactions | `idle_in_transaction_session_timeout` |
| Whole request | Reverse-proxy timeout; handlers should not outlive it |

Details and PgBouncer implications: [connection-pooling.md](connection-pooling.md).

## Health endpoints

```python
@router.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}          # process is up; no database access


@router.get("/health/ready")
async def ready(session: SessionDep, response: Response) -> dict[str, str]:
    try:
        await asyncio.wait_for(session.execute(text("SELECT 1")), timeout=2.0)
    except (SQLAlchemyError, OSError, TimeoutError):
        logger.exception("readiness check failed")
        response.status_code = 503
        return {"status": "unavailable"}
    return {"status": "ok"}
```

- Liveness must not depend on the database: a database outage would make
  the orchestrator restart healthy pods, adding load to recovery.
- Readiness checks the full path (pool, network, TLS, authentication)
  with a bounded timeout. It uses a pooled connection, so probes count
  against the pool.
- Do not return exception text to callers; log it server-side.
- Validated against a stopped database (connection refused): returns `503`.
- Server-side checks (replication lag, disk, locks):
  [14-observability/health-checks.md](../14-observability/health-checks.md).

## Common mistakes

- Blocking calls (`time.sleep`, `requests`, sync SQLAlchemy) in `async def`.
- One module-level `AsyncSession` or one shared between `gather()` tasks.
- Creating the engine at import time (breaks tests, fork-based workers,
  and shutdown); create it in `lifespan`.
- `?sslmode=...` in an asyncpg URL, or no TLS setting at all.
- Using `@app.on_event`, `session.query()`, or `declarative_base()` from
  1.x examples.
- Readiness probes that run expensive queries.

## Security considerations

- Verified TLS (above) and least-privilege role ([06-security/](../06-security/README.md)).
- `echo=True` logs bound parameter values; keep it off in production.
- Never put the database URL in logs or error responses; the example
  stores it as `pydantic.SecretStr`.

## Performance considerations

- asyncpg's binary protocol and prepared-statement cache speed repeated
  queries; they interact with PgBouncer, see
  [connection-pooling.md](connection-pooling.md#prepared-statements-with-asyncpg).
- With asyncpg and PostgreSQL `ENUM` types, new connections may run an
  expensive type-introspection query; the SQLAlchemy dialect docs suggest
  `connect_args={"server_settings": {"jit": "off"}}` as a mitigation.
- DDL run from another process can leave pooled connections with stale
  cached statements (`InvalidCachedStatementError`); restart or recycle
  application pods after migrations that change column types
  ([09-alembic/production-migrations.md](../09-alembic/production-migrations.md)).

## AI/agentic use case

Agent workers awaiting LLM or tool calls are the classic reason to choose
async. The rule still applies: do the slow call outside the transaction,
then open a short transaction to persist the result, so waiting on a model
never holds a pooled connection
([11-agentic-ai/](../11-agentic-ai/README.md)).

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `MissingGreenlet` | Lazy load or expired attribute outside an awaited call; use loader options |
| `TypeError: connect() got an unexpected keyword argument 'sslmode'` | Use `ssl=` or `connect_args={"ssl": ctx}` |
| `root certificate file ... does not exist` | `ssl=verify-full` without `~/.postgresql/root.crt`; pass an `SSLContext` |
| `InterfaceError: connection is closed` | Dead pooled connection; `pool_pre_ping=True` (reproduced by `pg_terminate_backend`) |
| `RuntimeError: ... attached to a different loop` | Engine created in one event loop and used in another (common in tests); create it inside the running loop |

## Quick revision

- Create the engine in `lifespan`; session via `Annotated[..., Depends]`; handler commits.
- Never block the event loop; never share an `AsyncSession` across tasks.
- asyncpg TLS: `connect_args={"ssl": ssl.create_default_context(cafile=...)}`; `?ssl=require` encrypts without verifying; `sslmode` is invalid.
- Liveness without the DB, readiness with a bounded `SELECT 1`.
- Sync and async are both valid; pick by workload and team, and do not mix them in one handler.
