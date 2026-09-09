# Database Design

## What it is

The schema decisions that outlive almost everything else in a system:
keys, constraints, normalization, indexing strategy, and naming. Code
gets rewritten; a schema mistake gets migrated around for years.

## Why it matters

Most production performance and correctness problems trace back to a
design decision made once, early, without much thought: no index on a
foreign key column, a missing `UNIQUE` constraint, a primary key type
that doesn't fit the access pattern.

## In this section

| Page | Covers |
|---|---|
| [schemas.md](schemas.md) | `CREATE SCHEMA`, namespacing, multi-tenant isolation |
| [primary-keys.md](primary-keys.md) | Identity columns, UUIDs (incl. UUIDv7), natural vs. surrogate keys |
| [foreign-keys.md](foreign-keys.md) | `REFERENCES`, `ON DELETE`/`ON UPDATE`, indexing the FK column |
| [constraints.md](constraints.md) | `CHECK`, `UNIQUE` (incl. `NULLS NOT DISTINCT`), `NOT NULL` |
| [normalization.md](normalization.md) | Normal forms, deliberate denormalization, JSONB |
| [indexes.md](indexes.md) | Index types, composite/partial/covering indexes, `CONCURRENTLY` |
| [naming-conventions.md](naming-conventions.md) | Identifier casing, singular/plural, PostgreSQL's default constraint names |

## Where to go next

- Writing the queries these tables will serve? See
  [02-sql-fundamentals/](../02-sql-fundamentals/).
- Need transaction/locking behavior around schema changes? See
  [04-transactions/](../04-transactions/).
- Tuning an existing index or diagnosing a slow query? See
  [05-performance/](../05-performance/).
- Applying schema changes safely in production? See
  [09-alembic/production-migrations.md](../09-alembic/production-migrations.md).
- Roles and grants for accessing these tables? See
  [06-security/](../06-security/).
