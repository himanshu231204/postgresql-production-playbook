# Primary Keys

## What it is

The column (or columns) that uniquely and non-`NULL`-ably identify a row.

## Why it matters

The primary key type is one of the hardest decisions to change later —
it's referenced by every foreign key pointing at the table, embedded in
every API response, and often baked into client-side caches and URLs.

## Syntax

```sql
-- Modern, SQL-standard identity column (PostgreSQL 10+) — prefer this over SERIAL
CREATE TABLE orders (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ...
);

-- UUID primary key
CREATE TABLE orders (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),  -- random (v4); built into core since PostgreSQL 13
  ...
);

CREATE TABLE orders (
  id UUID PRIMARY KEY DEFAULT uuidv7(),  -- time-ordered (v7); built into core since PostgreSQL 18
  ...
);

-- Composite primary key (e.g. a pure join table)
CREATE TABLE order_items (
  order_id BIGINT REFERENCES orders(id),
  product_id BIGINT REFERENCES products(id),
  PRIMARY KEY (order_id, product_id)
);
```

`SERIAL`/`BIGSERIAL` still work but are the older way to get an
auto-incrementing integer (they're sugar around a separate sequence with
looser ownership semantics). `GENERATED ALWAYS AS IDENTITY` is the
SQL-standard equivalent and the recommended choice for new tables.

## Tradeoffs: integer identity vs. UUID

| | `BIGINT IDENTITY` | `UUID` (v4, random) | `UUID` (v7, time-ordered) |
|---|---|---|---|
| Size | 8 bytes | 16 bytes | 16 bytes |
| Insert locality | Sequential — new rows append to the end of the index, cache-friendly | Random — new rows scatter across the index, causing more page splits and worse cache behavior on large tables | Mostly sequential (time-ordered prefix) — much closer to integer-identity insert behavior |
| Generate without a DB round-trip | No (needs the sequence) | Yes | Yes |
| Safe to expose in a public API/URL | Reveals row count and creation order (enumeration risk) — see "Security considerations" | Yes — not sequentially guessable | Encodes a timestamp, but not sequentially guessable across rows created close together |
| Natural merge across shards/services | No — collisions across independently-seeded sequences | Yes | Yes |

There's no universally correct choice. A single-database, single-writer
system with no need to generate IDs offline usually does fine with
`BIGINT IDENTITY`. A system that generates IDs in multiple places before
they reach the database (multiple services, offline/client-side
generation, merging data from several sources) needs UUIDs — prefer v7
over v4 for the insert-locality benefit unless you specifically need
UUIDs to be unpredictable in generation order too.

## Common mistakes

- Still defaulting to `SERIAL` out of habit — `GENERATED ALWAYS AS
  IDENTITY` is the modern equivalent with cleaner sequence ownership.
- Choosing `UUID` v4 for a high-write-volume table without realizing the
  index-locality cost, then being surprised by index bloat/cache misses
  under load.
- Conflating a primary key with an idempotency key. An agent's
  `tool_call` retry should be deduplicated by an explicit idempotency
  key/unique constraint (see
  [AGENTS.md](../AGENTS.md#12-agentic-ai-database-rules)), not by trying
  to predict or reuse a primary key value.

## Security considerations

A sequential integer primary key exposed in a URL (`/orders/1042`) leaks
the approximate row count and creation order, and makes enumerating
other rows trivial. If that matters for the resource, use a UUID (or a
separate opaque public identifier column) instead of the internal
primary key for anything user-facing.

## Performance considerations

`BIGINT IDENTITY` keeps the primary key's B-tree index small and
insert-friendly. If you need UUIDs, prefer `uuidv7()` (PostgreSQL 18+)
over `gen_random_uuid()` (v4) specifically to keep most of that
insert-locality benefit — the choice measurably affects index bloat and
cache hit rates on high-write tables.

## Quick revision

- Use `GENERATED ALWAYS AS IDENTITY`, not `SERIAL`, for new integer keys.
- UUID v4 is random and costs index locality; UUID v7 (PostgreSQL 18+) is
  time-ordered and much closer to integer-identity insert behavior.
- Don't expose a sequential integer PK where enumeration/leakage matters.
- Primary key ≠ idempotency key — model retried writes with their own
  unique constraint.
