# Connection Pooling in SQLAlchemy

Application-side counterpart of
[05-performance/connection-pooling.md](../05-performance/connection-pooling.md),
which covers why PostgreSQL connections are expensive, `max_connections`,
and PgBouncer pool modes. This page covers SQLAlchemy's own pool and how
it behaves in front of PgBouncer. Version: SQLAlchemy 2.1.3, asyncpg 0.31.0.
Code: [examples/fastapi-postgres/app/db.py](../examples/fastapi-postgres/app/db.py).

## What it is

`create_async_engine()` (or `create_engine()`) creates a pool of open
connections inside the Python process. A session checks a connection out
on its first statement and returns it on `commit()`, `rollback()`, or
`close()`. The default pool for async engines is `AsyncAdaptedQueuePool`
(defaults on 2.1.3: `pool_size=5`, `max_overflow=10`, `pool_timeout=30`,
`pool_recycle=-1`, `pool_pre_ping=False`).

## Why it matters

The pool is per process. Four Uvicorn workers with the defaults can open
`4 x (5 + 10) = 60` connections; ten pods can open 600. The database
sees the sum, and it fails closed: `FATAL: too many connections` or the
role's `CONNECTION LIMIT` rejects the next client.

## Settings

```python
engine = create_async_engine(
    DATABASE_URL,                 # from the environment
    pool_size=5,
    max_overflow=5,
    pool_timeout=10,
    pool_recycle=1800,
    pool_pre_ping=True,
    connect_args={"timeout": 10},  # asyncpg connect timeout, seconds
)
```

| Setting | Meaning | Tradeoff |
|---|---|---|
| `pool_size` | Connections kept open | Higher: fewer reconnects, more idle backends held on the server |
| `max_overflow` | Extra connections beyond `pool_size` under burst; closed when returned | Higher: absorbs bursts, raises the worst-case total |
| `pool_timeout` | Seconds a request waits for a free connection before `TimeoutError` | Lower: fails fast and sheds load; higher: requests queue and latency grows |
| `pool_recycle` | Reconnect connections older than N seconds, checked at checkout | Needed if a firewall, load balancer, or proxy drops long-lived connections; costs periodic reconnects. `-1` disables |
| `pool_pre_ping` | Test a connection at checkout, replace it if dead | One extra round trip per checkout; avoids handing a request a connection that died during a failover or restart. Does not help a connection that dies mid-request |
| `pool_use_lifo` | Reuse the most recently returned connection | Lets surplus connections go idle and be recycled; default is FIFO |

Related timeouts (not pool settings, but they bound how long a checked-out
connection can be held):

| Setting | Where | Effect |
|---|---|---|
| `connect_args={"timeout": s}` | asyncpg | Connection establishment |
| `connect_args={"command_timeout": s}` | asyncpg | Client-side default timeout per operation |
| `statement_timeout` | PostgreSQL | Server cancels statements running longer than this |
| `idle_in_transaction_session_timeout` | PostgreSQL | Server terminates sessions idle inside a transaction |
| `lock_timeout` | PostgreSQL | Give up waiting for a lock |

Prefer setting the PostgreSQL timeouts server-side per role:

```sql
-- PostgreSQL SQL, run by an administrator
ALTER ROLE app_api SET statement_timeout = '15s';
ALTER ROLE app_api SET idle_in_transaction_session_timeout = '30s';
```

They can also be sent as startup parameters
(`connect_args={"server_settings": {"statement_timeout": "15000"}}`, as
the example app does), but PgBouncer rejects startup parameters it does
not know unless they are listed in `ignore_startup_parameters`, and does
not guarantee per-client session settings in transaction mode.
Choose values from your own latency distribution; there is no universal number.

## Sizing

1. Server budget: `max_connections` minus `superuser_reserved_connections`
   minus other clients (migrations, monitoring, replicas' tools, humans).
   Also respect the role's `CONNECTION LIMIT`
   ([06-security/least-privilege.md](../06-security/least-privilege.md)).
2. Divide by the maximum number of processes that run at once,
   **including overlap during rolling deploys** (old and new pods both
   connected).
3. Set `pool_size + max_overflow` to that quotient or less.

```
worst case = processes x (pool_size + max_overflow)  <=  usable server connections
```

More connections than the database has cores to serve does not add
throughput; the extra requests queue either in the pool (cheap, bounded
by `pool_timeout`) or inside PostgreSQL (expensive). A small pool with
a short `pool_timeout` is usually easier to reason about than a large one.
Measure with `pg_stat_activity` grouped by `usename, application_name`
([14-observability/pg-stat-activity.md](../14-observability/pg-stat-activity.md))
and set `application_name` per service so the totals are attributable.

A connection is held from the first statement until the transaction ends,
so sizing depends on request concurrency x transaction duration, not on
request rate. Anything slow inside a transaction (an HTTP call, an LLM
call) multiplies the number of connections needed.

## With PgBouncer

PgBouncer transaction mode multiplexes many client connections onto a
few server connections, so the app pool and the PgBouncer pool are two
separate layers. Pool modes are described in
[05-performance/connection-pooling.md](../05-performance/connection-pooling.md#pgbouncer-pool-modes).

Application-side choices:

| Option | Effect | Tradeoff |
|---|---|---|
| Keep the SQLAlchemy pool, point the URL at PgBouncer | App connections to PgBouncer stay open; PgBouncer assigns a server connection per transaction | Cheapest per request. Anything cached per connection on the client side (asyncpg prepared statements) must survive the server connection changing |
| `poolclass=NullPool` | Open and close a PgBouncer client connection on every checkout | The pattern in the SQLAlchemy asyncpg docs; avoids stale per-connection state, but pays connection setup (and TLS) per checkout |

### Prepared statements with asyncpg

The SQLAlchemy asyncpg dialect prepares every statement and caches the
prepared statements per DBAPI connection (default
`prepared_statement_cache_size=100`); asyncpg has its own cache
(`statement_cache_size=100`). In transaction mode the server connection
can change between transactions, which can surface as
`prepared statement "..." already exists` or `does not exist` errors.

| PgBouncer | What to do |
|---|---|
| Tracks protocol-level prepared statements: `max_prepared_statements` greater than 0 (PgBouncer 1.21 and later; documented default `200`) | Statements are re-prepared on the server connection transparently; keep the caches enabled. Verify with your versions under load before relying on it |
| Older PgBouncer, or `max_prepared_statements = 0` | Disable both caches and use unique statement names, as below |

Configuration documented in the SQLAlchemy asyncpg dialect page for the
no-tracking case:

```python
from uuid import uuid4

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

engine = create_async_engine(
    "postgresql+asyncpg://app_api:PASSWORD@pgbouncer-host:6432/appdb",
    poolclass=NullPool,
    connect_args={
        "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
        "prepared_statement_cache_size": 0,   # SQLAlchemy's cache
        "statement_cache_size": 0,            # asyncpg's own cache
    },
)
```

The SQLAlchemy docs warn that with PgBouncer you should use `NullPool`
and configure PgBouncer to run `DISCARD` when returning connections, to
avoid accumulating prepared statements. PgBouncer does not run
`server_reset_query` in transaction mode unless `server_reset_query_always = 1`.
The example project exposes this as `DB_USE_NULL_POOL=true` and
`DB_DISABLE_STATEMENT_CACHE=true`.

Other transaction-mode caveats: do not rely on session-level `SET`,
`LISTEN/NOTIFY`, session advisory locks, or temporary tables across
transactions; use `SET LOCAL` inside the transaction instead. The
example project was not run against PgBouncer; validate this
configuration in a staging environment with your PgBouncer version.

Also keep PgBouncer's own limits consistent: its `default_pool_size`
x number of (database, user) pairs bounds server connections, while
`max_client_conn` bounds what applications may open.

## Failure behavior

| Event | Pool behavior |
|---|---|
| Database restart or failover | Existing connections are dead. With `pool_pre_ping=True` the next checkout replaces them; without it, one request per dead connection fails |
| Pool exhausted | After `pool_timeout`, `sqlalchemy.exc.TimeoutError: QueuePool limit of size N overflow M reached, connection timed out` |
| Client cancelled or request aborted mid-query | The connection is invalidated or rolled back before reuse; do not catch and continue using the same session after a cancellation |
| `engine.dispose()` | Closes pooled connections; call at shutdown (done in `lifespan`) |

## Common mistakes

- Using default pool settings with many workers/pods and exhausting
  `max_connections`.
- Creating an engine per request or per call: every request pays full
  connection setup and the pool is never reused. Create one engine per
  process.
- Raising `max_overflow` to hide slow queries or long transactions.
- Forgetting that `fork`-ed workers (Gunicorn `--preload`) must not
  share an engine created before the fork; create it in `lifespan`.
- PgBouncer transaction mode with default asyncpg caches and no
  prepared-statement tracking.
- Holding a session open across `await` calls to slow services.

## Troubleshooting

| Symptom | Check |
|---|---|
| `QueuePool limit ... reached` | Transactions held too long (look for `idle in transaction` in `pg_stat_activity`), pool smaller than request concurrency, leaked sessions (missing `async with`) |
| `FATAL: too many connections` / role limit reached | Sum across all processes exceeds budget; see [15-production-runbooks/connection-exhaustion.md](../15-production-runbooks/connection-exhaustion.md) |
| `InterfaceError: connection is closed` / `connection was closed in the middle of operation` | Idle connection dropped by a proxy or server restart; set `pool_pre_ping=True` and `pool_recycle` below the proxy's idle timeout |
| `prepared statement ... already exists` | PgBouncer transaction mode with caches on; see above |

```sql
-- PostgreSQL SQL: who holds connections, by service
SELECT usename, application_name, state, count(*)
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY 1, 2, 3
ORDER BY 4 DESC;
```

## Quick revision

- Pool is per process: `processes x (pool_size + max_overflow)` must fit the server.
- `pool_pre_ping` for restarts/failovers, `pool_recycle` for idle-dropping middleboxes, short `pool_timeout` to shed load.
- Set `statement_timeout` and `idle_in_transaction_session_timeout` on the role.
- PgBouncer transaction mode + asyncpg: tracked prepared statements (`max_prepared_statements` > 0), or `NullPool` + both caches off + unique names.
- One engine per process, created in `lifespan`, disposed at shutdown.
