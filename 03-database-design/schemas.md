# Schemas

## What it is

A namespace inside a database that holds tables, views, and other
objects. Every database has a default `public` schema; you can create
more.

## Why it matters

Schemas are one of two common ways to isolate data within a single
database (the other being a `tenant_id` column on shared tables) — the
choice affects security, backup/restore granularity, and query
complexity for the life of the system.

## Syntax

```sql
CREATE SCHEMA billing;
CREATE TABLE billing.invoices (...);

-- Which schemas are searched, and in what order, for unqualified names:
SHOW search_path;
SET search_path TO billing, public;
```

## Production usage: schema-per-tenant vs. shared schema

| Approach | Isolation | Cost |
|---|---|---|
| One schema per tenant | Strong — a bug in one tenant's query can't leak into another's data by accident; per-tenant backup/restore is straightforward | Migrations must run once per schema (per tenant); doesn't scale cleanly past a few hundred tenants |
| Shared schema, `tenant_id` column on every table | One set of tables, one migration run, scales to many tenants easily | Every query must remember to filter by `tenant_id` — a missed filter is a cross-tenant data leak; enforce with row-level security (see [06-security/](../06-security/)) rather than trusting every query author |

Neither is universally correct — schema-per-tenant suits a smaller number
of larger tenants; a shared schema with row-level security suits a large
number of smaller tenants.

## Common mistakes

- Relying on the default `search_path` (`"$user", public`) instead of
  fully qualifying table names (`schema.table`) in application code —
  ambiguous when multiple schemas define a same-named table.
- Granting a role `SELECT` on a table without also granting `USAGE` on
  its schema — the role still can't reach the table. `USAGE` on the
  schema is a separate, required permission.
- Assuming schemas provide the same isolation as separate databases —
  they don't protect against a superuser or a role with broad grants
  across schemas.

## Security considerations

`GRANT USAGE ON SCHEMA billing TO app_role;` is required before any
table-level grant inside that schema takes effect for that role. See
[06-security/permissions.md](../06-security/permissions.md).

## AI/agentic use case

A multi-tenant AI platform storing per-tenant `conversations`/`messages`
faces the same schema-per-tenant vs. shared-schema-with-`tenant_id`
choice as any other multi-tenant system — see
[11-agentic-ai/](../11-agentic-ai/) for the schema shapes involved either
way.

## Quick revision

- `CREATE SCHEMA name;` then `schema.table` to reference objects in it.
- `GRANT USAGE ON SCHEMA` is required in addition to table-level grants.
- Schema-per-tenant = strong isolation, doesn't scale to many tenants;
  shared schema + `tenant_id` = scales, needs row-level security to stay
  safe.
