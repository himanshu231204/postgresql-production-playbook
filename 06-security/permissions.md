# Permissions

## What it is

Privileges control what a role may do to a database object: `CONNECT`
on a database, `USAGE`/`CREATE` on a schema, `SELECT`/`INSERT`/
`UPDATE`/`DELETE` on a table, `USAGE` on a sequence, `EXECUTE` on a
function. They are managed with `GRANT` and `REVOKE`.

## Why it matters

A role can only be as constrained as the grants you actually wrote — and
the defaults grant more than most people expect (the `PUBLIC`
pseudo-role, below).

## Syntax

**PostgreSQL SQL**, run as the object owner or an admin role.

```sql
GRANT CONNECT ON DATABASE appdb TO app_rw;
GRANT USAGE ON SCHEMA app TO app_rw;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app TO app_rw;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA app TO app_rw;

-- Column-level: allow reading only non-sensitive columns.
GRANT SELECT (id, email) ON app.users TO app_readonly;

REVOKE DELETE ON app.users FROM app_rw;
```

`ON ALL TABLES IN SCHEMA` covers only tables that exist **now**. Tables
created later need `ALTER DEFAULT PRIVILEGES`.

## The `PUBLIC` pseudo-role

`PUBLIC` means every role, present and future. By default:

- Every role may `CONNECT` to a new database and create temporary
  tables in it (`TEMPORARY`).
- Every role may `EXECUTE` newly created functions.
- PostgreSQL 14 and earlier: every role also had `CREATE` and `USAGE` on
  the `public` schema. **PostgreSQL 15 removed `CREATE` on `public` from
  `PUBLIC`** (the database owner keeps it), but `USAGE` remains.

Harden a new database:

```sql
REVOKE ALL ON DATABASE appdb FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;   -- redundant on 15+, required on 14 and earlier
```

Then grant `CONNECT` back to specific roles. Use application-owned
schemas instead of `public` (see
[03-database-design/schemas.md](../03-database-design/schemas.md)).

## Default privileges for future objects

```sql
-- Objects created by migration_owner in schema app automatically
-- get these grants:
ALTER DEFAULT PRIVILEGES FOR ROLE migration_owner IN SCHEMA app
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_rw;
ALTER DEFAULT PRIVILEGES FOR ROLE migration_owner IN SCHEMA app
    GRANT USAGE, SELECT ON SEQUENCES TO app_rw;
```

Default privileges apply only to objects created by the named role
(`FOR ROLE`), after the statement runs. Omit `FOR ROLE` and it applies
to the role running the statement — a frequent source of "the new table
has no grants" after a migration runs as a different role.

## Row-level security

Restricts which **rows** a role sees, enforced by the database rather
than by application `WHERE` clauses.

```sql
ALTER TABLE app.documents ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON app.documents
    FOR ALL TO app_rw
    USING (tenant_id = current_setting('app.tenant_id')::uuid)
    WITH CHECK (tenant_id = current_setting('app.tenant_id')::uuid);
```

- The table owner and roles with `BYPASSRLS` skip policies; use
  `ALTER TABLE ... FORCE ROW LEVEL SECURITY` to apply them to the owner
  too (superusers always bypass).
- With RLS enabled and no policy, non-owner roles see no rows.
- Set the tenant per transaction with `SET LOCAL app.tenant_id = '...'`
  (or `set_config('app.tenant_id', ..., true)`), not per session, so a
  pooled connection cannot carry one tenant's value into another's
  request (see
  [05-performance/connection-pooling.md](../05-performance/connection-pooling.md)).
- RLS adds a predicate to every query: index the policy column and
  confirm the plan with `EXPLAIN` (see
  [05-performance/explain.md](../05-performance/explain.md)).

## Auditing existing grants

| Command | Type | Purpose |
|---|---|---|
| `\dp app.*` (alias `\z`) | psql meta-command | Table/sequence privileges (`arwd...` access-privilege codes) |
| `\ddp` | psql meta-command | Default privileges |
| `\dn+` | psql meta-command | Schemas with their ACLs |
| `SELECT has_table_privilege('app_rw', 'app.users', 'DELETE');` | PostgreSQL SQL | Check one effective privilege (follows inheritance) |
| `SELECT grantee, table_schema, table_name, privilege_type FROM information_schema.role_table_grants WHERE grantee = 'PUBLIC' AND table_schema NOT IN ('information_schema', 'pg_catalog');` | PostgreSQL SQL | Find grants to `PUBLIC` |

`\dp` shows privilege letters: `r` SELECT, `a` INSERT, `w` UPDATE,
`d` DELETE, `D` TRUNCATE, `x` REFERENCES, `t` TRIGGER. A trailing
`/owner` is the grantor.

## Common mistakes

- `GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA ...` to an application
  role: includes `TRUNCATE`, `REFERENCES`, `TRIGGER` it never needs.
  Grant the CRUD set only.
- Forgetting sequence privileges: `INSERT` into a table with a
  `serial`/`IDENTITY` column fails with `permission denied for sequence`
  unless the role has `USAGE` on the sequence.
- Granting on existing tables but not setting default privileges, so the
  next migration's tables are inaccessible to the application.
- Relying on an application-level `WHERE tenant_id = ...` as the only
  tenant isolation, with no database enforcement.

## Security considerations

BAD — broad, ongoing:

```sql
GRANT ALL PRIVILEGES ON DATABASE appdb TO app_api;
GRANT ALL ON ALL TABLES IN SCHEMA public TO app_api;
```

GOOD — scoped to the schema and the verbs the code uses:

```sql
GRANT CONNECT ON DATABASE appdb TO app_rw;
GRANT USAGE ON SCHEMA app TO app_rw;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app TO app_rw;
```

Revoking is also destructive to running systems: `REVOKE` takes effect
for new statements immediately and can break a live application. Check
usage first (`pg_stat_activity`, logs) and apply during a controlled
change.

## Quick revision

- Revoke the defaults from `PUBLIC` on each new database.
- `GRANT ... ON ALL TABLES` is a snapshot; pair it with `ALTER DEFAULT
  PRIVILEGES FOR ROLE <creator>`.
- Tables need `SELECT/INSERT/UPDATE/DELETE`; identity/serial columns
  need sequence `USAGE`.
- RLS is enforced per role; owners and `BYPASSRLS` roles skip it unless
  `FORCE` is set.
