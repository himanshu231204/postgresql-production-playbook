# Connection Pooling

This page covers the general/infrastructure angle: why connections are
expensive and how an external pooler like PgBouncer works. For
configuring pooling from the application side (SQLAlchemy's own pool
settings), see
[08-python-fastapi/connection-pooling.md](../08-python-fastapi/connection-pooling.md).

## What it is

Reusing a small number of actual PostgreSQL connections across a much
larger number of application requests/workers, instead of opening a new
connection per request.

## Why it matters

PostgreSQL forks a new OS process per connection — unlike a
thread-per-connection model, this makes each connection meaningfully
more expensive to set up and hold idle than in many other databases.
An application that opens a new connection per request, at any real
scale, spends a surprising amount of time and memory on connection
setup instead of query execution.

## `max_connections`

PostgreSQL's hard ceiling on concurrent connections, set in
`postgresql.conf`. Raising it isn't free: each potential connection
reserves memory up front (and more once actually connected, for
per-connection work memory), so `max_connections` is sized against
available RAM, not just "how many clients might connect."

## Why pool instead of just raising `max_connections`

A connection pooler sits between the application and PostgreSQL,
multiplexing many application-side connections onto a smaller number of
real PostgreSQL backend connections. This keeps `max_connections`
modest while still serving many concurrent application requests —
important because each PostgreSQL backend process has real memory and
scheduling overhead regardless of how idle it is.

## PgBouncer pool modes

| Mode | Backend connection lifetime | Compatibility |
|---|---|---|
| `session` | Held for the entire client session, start to disconnect | Full compatibility — session-level features (`SET`, `LISTEN`/`NOTIFY`, prepared statements, advisory locks held across transactions) all work normally; least efficient reuse |
| `transaction` | Returned to the pool after each `COMMIT`/`ROLLBACK` | Most common choice for web applications; breaks anything that relies on session state persisting between transactions, unless the pooler is configured to track it (modern PgBouncer versions support tracking prepared statements across transaction-mode connections when explicitly configured for it) |
| `statement` | Returned to the pool after each statement | Most aggressive reuse; effectively incompatible with multi-statement transactions — rarely appropriate for general application traffic |

**Transaction mode is the common default for stateless web application
traffic** — it gives most of the efficiency benefit while fitting how
most request-scoped database usage already looks (one or a few
statements per request, no session state relied on across requests).
Session mode is for cases that genuinely need session-level features
(a long-lived worker relying on advisory locks or session-level `SET`,
for instance).

## Common mistakes

- Raising `max_connections` to work around connection exhaustion instead
  of adding a pooler — this trades one resource limit for a different,
  often worse one (memory pressure from many idle backend processes).
- Using transaction-mode pooling with application code that relies on
  session-level state (a prepared statement created once and reused, a
  `SET` that's expected to persist, an advisory lock held across
  multiple transactions) without accounting for the mismatch.
- Sizing a pool by guessing instead of by request concurrency and how
  long a typical transaction holds its connection.

## AI/agentic use case

An agent orchestrator that spins up many concurrent worker
processes/tasks, each opening its own short-lived database connection to
check or update `workflow_state`, is exactly the pattern connection
pooling exists for — see
[11-agentic-ai/](../11-agentic-ai/).

## Quick revision

- PostgreSQL connections are process-based and comparatively expensive
  — pool them rather than opening one per request.
- `max_connections` is a memory-bounded ceiling, not a dial to turn up
  freely.
- PgBouncer transaction mode is the common default; session mode only
  when session-level state is genuinely needed.
