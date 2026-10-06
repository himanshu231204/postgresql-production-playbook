# Least Privilege

## What it is

Give each credential only the privileges its job needs. For an
application database that means three distinct roles, matching
[AGENTS.md](../AGENTS.md#7-security-rules):

| Role | Used by | Privileges |
|---|---|---|
| `app_api` (member of `app_rw`) | Running application | `CONNECT`, `USAGE` on schema, `SELECT/INSERT/UPDATE/DELETE` on tables, sequence `USAGE` |
| `migration_owner` | Alembic / deploy pipeline | Owns the schema and its objects; runs DDL; no use at runtime |
| `dba_admin` | Humans, break-glass | Administrative control; not a shared or application credential |

## Why it matters

The application is the most exposed component: SQL injection, a
compromised dependency, or a leaked `DATABASE_URL` all act with the
application role's privileges. If that role cannot run DDL, drop tables,
or read other schemas, the blast radius shrinks to what the application
legitimately does.

## Example: complete setup

**PostgreSQL SQL**, PostgreSQL 16. Run as a superuser or equivalent
admin. Passwords are not set here; see
[passwords-and-secrets.md](passwords-and-secrets.md).

```sql
-- 1. Roles
CREATE ROLE migration_owner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
CREATE ROLE app_rw NOLOGIN;
CREATE ROLE app_api LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
    CONNECTION LIMIT 50;
GRANT app_rw TO app_api;

-- 2. Database and schema owned by the migration role
CREATE DATABASE appdb OWNER migration_owner;
REVOKE ALL ON DATABASE appdb FROM PUBLIC;
GRANT CONNECT ON DATABASE appdb TO app_rw, migration_owner;
```

```sql
-- 3. Inside appdb (psql: \c appdb)
CREATE SCHEMA app AUTHORIZATION migration_owner;
REVOKE ALL ON SCHEMA public FROM PUBLIC;

GRANT USAGE ON SCHEMA app TO app_rw;

-- 4. Grants for objects migration_owner creates from now on
ALTER DEFAULT PRIVILEGES FOR ROLE migration_owner IN SCHEMA app
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_rw;
ALTER DEFAULT PRIVILEGES FOR ROLE migration_owner IN SCHEMA app
    GRANT USAGE, SELECT ON SEQUENCES TO app_rw;

-- 5. Make the app role resolve unqualified names in the right schema
ALTER ROLE app_api SET search_path = app;
```

Run migrations connected as `migration_owner`, so tables are owned by it
and receive the default privileges above. The application connects as
`app_api` and cannot `CREATE`, `ALTER`, `DROP`, or `TRUNCATE`.

Verify, connected as a superuser in `appdb`:

```sql
SELECT has_schema_privilege('app_api', 'app', 'CREATE');          -- false
SELECT has_schema_privilege('app_api', 'app', 'USAGE');           -- true
SELECT has_database_privilege('app_api', 'appdb', 'CREATE');      -- false
```

## Production usage

- Keep the migration role's credential in the deploy pipeline only, not
  in the running application's environment. See
  [09-alembic/production-migrations.md](../09-alembic/production-migrations.md).
- Use a separate read-only role (`SELECT` only) for analytics, reporting,
  and read replicas' consumers.
- Use `SET ROLE` or distinct credentials for humans; log in as a named
  role, not a shared `dba_admin` password.
- Reconcile with `\dp` and `\ddp` after each migration that adds schemas
  or tables (see [permissions.md](permissions.md#auditing-existing-grants)).

## Common mistakes

- Running migrations as the application role: the app then needs DDL
  privileges at runtime, defeating the split.
- Running migrations as a superuser: new tables are owned by `postgres`
  and `ALTER DEFAULT PRIVILEGES FOR ROLE migration_owner` never applies
  to them.
- Granting the application role membership in the owner role
  (`GRANT migration_owner TO app_api`) as a shortcut: it inherits DDL.
- A legitimate need for DDL at runtime (for example, per-tenant tables
  created by the app) handled by widening `app_api` instead of a
  separate, narrowly scoped role or a security-definer function.

## Security considerations

- Superuser-only functionality (`COPY ... TO PROGRAM`, `pg_read_server_files`,
  extensions that run arbitrary code) must be unreachable from the
  application role.
- `SECURITY DEFINER` functions run with the owner's privileges: set
  `SET search_path = ...` on them and `REVOKE EXECUTE ... FROM PUBLIC`
  before granting to specific roles.
- For AI/agent workloads, treat tool-executing database roles as
  untrusted-input consumers: give agents a role limited to the specific
  tables and verbs the tool needs, and never LLM-generated SQL under a
  write-capable role (see
  [11-agentic-ai/tool-calls.md](../11-agentic-ai/tool-calls.md)).

## Quick revision

- Three roles: application (CRUD), migration (DDL/owner), admin
  (human, break-glass).
- Migration role owns the objects; `ALTER DEFAULT PRIVILEGES FOR ROLE
  migration_owner` grants the app role access to future tables.
- Verify with `has_*_privilege()` and `\dp`; never assume.
