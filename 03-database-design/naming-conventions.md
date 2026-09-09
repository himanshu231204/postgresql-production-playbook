# Naming Conventions

## What it is

Consistent rules for naming tables, columns, keys, and indexes.

## Why it matters

PostgreSQL folds unquoted identifiers to lowercase, which makes `snake_case`
the path of least resistance — fighting that convention means quoting
identifiers everywhere, forever, including in every tool and migration
that touches the schema.

## Recommended conventions

| Object | Convention | Example |
|---|---|---|
| Tables, columns | `snake_case`, all lowercase | `order_items`, `created_at` |
| Table names | Plural (a table holds a collection of rows) — a defensible alternative is consistent singular naming; the important part is picking one and applying it everywhere | `orders`, not `order` |
| Primary key column | `id` | `orders.id` |
| Foreign key column | `<referenced_table_singular>_id` | `orders.customer_id` referencing `customers.id` |
| Timestamps | `_at` suffix, `TIMESTAMPTZ` type | `created_at`, `updated_at` |
| Boolean columns | `is_`/`has_` prefix | `is_active`, `has_verified_email` |
| Indexes | `idx_<table>_<column(s)>` | `idx_orders_customer_id` |

## PostgreSQL's default constraint names

If you don't name a constraint explicitly, PostgreSQL generates one
following its own pattern — worth knowing so error messages and
`\d table` output make sense:

| Constraint | Default name pattern | Example |
|---|---|---|
| Primary key | `<table>_pkey` | `orders_pkey` |
| Foreign key | `<table>_<column>_fkey` | `orders_customer_id_fkey` |
| Unique | `<table>_<column>_key` | `users_email_key` |
| Check | `<table>_<column>_check` | `subscriptions_seats_check` |

Naming constraints explicitly (`CONSTRAINT orders_customer_id_fkey
FOREIGN KEY ...`) instead of relying on the auto-generated name makes
migrations that later need to reference or drop that constraint by name
more predictable — the auto-generated name can change if the column is
renamed.

## Common mistakes

- Mixing casing (`CamelCase`/`camelCase` columns) — forces double-quoting
  that identifier in every query, forever, since PostgreSQL only
  case-folds *unquoted* identifiers.
- Inconsistent singular/plural table naming across the same schema.
- Relying on auto-generated constraint names in a migration that will
  later need to reference them, instead of naming the constraint
  explicitly up front.

## Quick revision

- `snake_case`, all lowercase, no quoting needed.
- Pick singular or plural for table names and stay consistent.
- `<table>_id` for foreign keys, `_at` + `TIMESTAMPTZ` for timestamps.
- Name constraints explicitly if a migration will need to reference them
  later.
