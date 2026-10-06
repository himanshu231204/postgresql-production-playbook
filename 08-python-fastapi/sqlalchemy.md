# SQLAlchemy 2.x with PostgreSQL

Version: SQLAlchemy 2.1.3 (2.x style throughout). Code:
[examples/sqlalchemy-postgres/](../examples/sqlalchemy-postgres/README.md).

## What it is

SQLAlchemy is a Python SQL toolkit and ORM. In 2.x style you declare
models with `Mapped[...]`/`mapped_column()`, build statements with
`select()`, and execute them through a `Session` or `AsyncSession`.
Legacy `session.query()` and 1.x imperative mapping are not used here.

## Why it matters

The ORM decides how many statements a request issues, how long a
transaction holds locks, and whether user input reaches SQL as a bound
parameter. These are production properties, not style choices.

## Syntax

### Models

```python
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, MetaData, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    metadata = MetaData(schema="app")  # explicit schema, not search_path


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    email: Mapped[str] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    orders: Mapped[list["Order"]] = relationship(lazy="raise")
```

- Models mirror tables; constraints that matter (`NOT NULL`, `UNIQUE`,
  `CHECK`, FKs with `ON DELETE`) are enforced by the database DDL, see
  [03-database-design/constraints.md](../03-database-design/constraints.md).
  `Base.metadata.create_all()` is for tests; production schema changes
  go through [Alembic](../09-alembic/README.md).
- Use `DateTime(timezone=True)` (`timestamptz`) for any value crossing
  services or time zones.

### Queries

```python
from sqlalchemy import select

stmt = select(Customer).where(Customer.email == email).limit(1)
customer = (await session.scalars(stmt)).one_or_none()   # AsyncSession
# customer = session.scalars(stmt).one_or_none()          # Session
```

`session.scalars()` returns ORM objects; `session.execute()` returns
rows. Both emit parameterized SQL (`WHERE email = $1`).

## Parameterized queries only

BAD, user input formatted into SQL (SQL injection):

```python
await session.execute(text(f"SELECT * FROM app.customers WHERE email = '{email}'"))
```

GOOD, bound parameter:

```python
from sqlalchemy import text

await session.execute(
    text("SELECT id FROM app.customers WHERE email = :email"), {"email": email}
)
```

Identifiers (table or column names) cannot be bound. Choose them from an
allow-list in code, never from request data.

## Transactions

A session starts a transaction automatically on first use ("autobegin")
and keeps it open until `commit()`, `rollback()`, or `close()`.

| Pattern | Behavior |
|---|---|
| `await session.commit()` | Commits; the next use autobegins a new transaction |
| `async with session.begin(): ...` | Commits on success, rolls back on exception; raises if a transaction is already begun |
| `async with sessionmaker.begin() as session:` | Session and transaction scoped together |
| `async with session.begin_nested(): ...` | `SAVEPOINT`; failure rolls back only the nested block |
| leaving `async with sessionmaker() as session:` | `close()`: releases the connection, rolls back anything uncommitted |

Rules:

- One transaction per request, committed by the handler once the unit of
  work is complete. See [repository-pattern.md](repository-pattern.md).
- Do not call slow external services (HTTP, LLM calls) inside an open
  transaction: it holds a pooled connection, and any row locks, for the
  duration. Do the call first, then open the transaction to record the
  result. Idle-in-transaction sessions block `VACUUM` and hold locks, see
  [04-transactions/locking.md](../04-transactions/locking.md).
- `async_sessionmaker(engine, expire_on_commit=False)`: with the default
  (`True`) every attribute is expired on commit and reading it triggers an
  implicit lazy load, which fails under asyncio.
- `flush()` sends pending SQL inside the transaction; only `commit()`
  makes it durable. Repositories flush; callers commit.
- Handle constraint violations with a savepoint so the session stays
  usable, and branch on the SQLSTATE rather than the message text:

```python
try:
    async with session.begin_nested():
        session.add(customer)
        await session.flush()
except IntegrityError as exc:
    if getattr(exc.orig, "sqlstate", None) == "23505":   # unique_violation
        raise DuplicateEmailError(email) from exc
    raise
```

`exc.orig.sqlstate` was verified with asyncpg 0.31.0 on PostgreSQL 16.
Re-check it if you use another driver.

## N+1 queries and loader strategies

N+1: one query for N parent rows, then one query per parent for its
children. It is invisible in development (few rows) and expensive in
production (N network round trips).

| Strategy | SQL | Use when | Tradeoff |
|---|---|---|---|
| `selectinload(Customer.orders)` | Second query: `WHERE customer_id IN (...)` | One-to-many collections | Two statements; no row multiplication. The child FK needs an index |
| `joinedload(Order.customer)` | One `JOIN` | Many-to-one, or one-to-one | On collections the result rows multiply and 2.x requires `.unique()` on the result; wide parents are re-sent per child row |
| `lazy="raise"` on the relationship | Raises on implicit load | Default for async code | Forces an explicit loader at each query site |
| Lazy `select` (default) | One query per access | Never in async: raises `MissingGreenlet` | N+1 in sync code |

```python
stmt = (
    select(Customer)
    .order_by(Customer.id)
    .limit(20)
    .options(selectinload(Customer.orders))
)
```

Detect N+1 by counting statements. `examples/sqlalchemy-postgres/demo_async.py`
registers a `before_cursor_execute` event and prints, for 5 customers:
the hand-written N+1 loop issues 6 statements, `selectinload` issues 2.
In production use `pg_stat_statements` and
[05-performance/query-optimization.md](../05-performance/query-optimization.md);
run `EXPLAIN (ANALYZE, BUFFERS)` on the statements SQLAlchemy emits
([05-performance/explain.md](../05-performance/explain.md)).

`selectinload` is only fast if the child foreign-key column is indexed:
PostgreSQL does not index FK columns automatically. The index
`orders (customer_id, id)` in `sql/02_schema.sql` serves both the list
query and the `IN (...)` query; the cost is one more index maintained on
every `INSERT` into `orders` ([03-database-design/indexes.md](../03-database-design/indexes.md)).

## Pagination

Prefer keyset pagination for lists that can grow:

```python
stmt = select(Customer).where(Customer.id > after_id).order_by(Customer.id).limit(50)
```

`OFFSET n` makes PostgreSQL read and discard `n` rows on every page.
Keyset needs a stable, indexed sort key and gives "next page" rather
than "page 40".

## Common mistakes

- One global `Session` shared by all requests (not safe for concurrent use).
- Reading a lazy relationship after the request's session closed.
- Committing inside repositories, so a handler cannot make two writes atomic.
- Using `session.execute(text(f"..."))` with interpolated input.
- Catching `Exception` around `flush()` instead of `IntegrityError`
  (hides real faults); catching it without a savepoint, leaving the
  transaction aborted.
- Relying on `Base.metadata.create_all()` in production startup.
- Logging `echo=True` output in production: it contains bound values.

## Security considerations

- Bound parameters for every value; allow-list identifiers.
- The application role has DML only; ORM models cannot `DROP` anything
  it has no privilege for ([06-security/least-privilege.md](../06-security/least-privilege.md)).
- Treat LLM output as untrusted input: validate with a Pydantic model
  before it reaches `session.add()`; never execute generated SQL under
  the write-capable role ([11-agentic-ai/tool-calls.md](../11-agentic-ai/tool-calls.md)).

## Performance considerations

- Select only what is needed: use `select(Customer.id, Customer.email)`
  or `load_only()` for wide rows.
- Bulk work: `session.execute(insert(Order), [{...}, {...}])` batches
  rows; adding thousands of ORM objects one by one is much slower.
- Long result sets: `await session.stream_scalars(stmt)` avoids
  buffering everything in memory.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `MissingGreenlet` | Implicit lazy load or expired attribute under asyncio; add a loader option or `expire_on_commit=False` |
| `InvalidRequestError` on `.orders` with `lazy="raise"` | Intended; add `selectinload(...)` to the query |
| `PendingRollbackError` | A flush failed and the transaction was not rolled back; use a savepoint or `rollback()` |
| `IntegrityError` ... `23505` / `23503` | Unique / foreign-key violation; map to 409 / 404 |
| `sqlalchemy.exc.TimeoutError: QueuePool limit ...` | Pool exhausted; see [connection-pooling.md](connection-pooling.md#troubleshooting) |

## Quick revision

- `Mapped`/`mapped_column`, `select()`, `Session`/`AsyncSession` only.
- Bound parameters always; identifiers from allow-lists.
- Handler commits; repositories flush; savepoint around expected failures.
- `selectinload` for collections, `lazy="raise"` to catch N+1, index the FK.
- Keyset pagination over `OFFSET`.
