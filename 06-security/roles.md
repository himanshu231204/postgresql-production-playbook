# Roles

## What it is

PostgreSQL has one concept for users and groups: the **role**. A role
that can log in is what other systems call a user; a role that cannot
log in and only holds privileges and members is what they call a group.
Roles are cluster-wide (shared across all databases in the cluster),
not per-database.

## Why it matters

Every connection authenticates as exactly one role, and every privilege
check starts from that role. Splitting roles by purpose (see
[least-privilege.md](least-privilege.md)) is what limits the damage
when one credential leaks.

## Syntax

These are **PostgreSQL SQL** statements, run in `psql` as a role with
`CREATEROLE` (PostgreSQL 16: with the necessary admin option on the
target roles) or as a superuser.

```sql
-- Login role (a "user"). Set the password interactively, see below.
CREATE ROLE app_api LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
    CONNECTION LIMIT 50;

-- Group role: holds privileges, cannot log in.
CREATE ROLE app_rw NOLOGIN;

-- Membership: app_api receives app_rw's privileges.
GRANT app_rw TO app_api;

ALTER ROLE app_api CONNECTION LIMIT 80;
ALTER ROLE app_api SET statement_timeout = '30s';
ALTER ROLE app_api SET idle_in_transaction_session_timeout = '60s';

REVOKE app_rw FROM app_api;
DROP ROLE app_api;   -- destructive: see "Common mistakes"
```

`CREATE USER` is `CREATE ROLE` with `LOGIN` as the default;
`CREATE GROUP` is an alias for `CREATE ROLE`. Prefer `CREATE ROLE` so
the attributes are explicit.

## Inspecting roles

| Command | Type | Purpose |
|---|---|---|
| `\du` / `\du+` | psql meta-command | List roles and attributes (`+` adds descriptions) |
| `\drg` | psql meta-command | List role memberships (PostgreSQL 16+) |
| `SELECT rolname, rolsuper, rolcreaterole, rolcreatedb, rolreplication, rolbypassrls, rolcanlogin, rolconnlimit FROM pg_roles ORDER BY rolname;` | PostgreSQL SQL | Same data in queryable form |
| `SELECT roleid::regrole, member::regrole, grantor::regrole, admin_option, inherit_option, set_option FROM pg_auth_members;` | PostgreSQL SQL | Memberships; `inherit_option`/`set_option` columns exist in PostgreSQL 16+ |
| `SELECT current_user, session_user;` | PostgreSQL SQL | Which role is the connection acting as |

Expected result: `\du` prints one row per role with attributes such as
`Superuser, Create role, Create DB, Cannot login`.

## Role attributes that matter in production

| Attribute | Effect | Production note |
|---|---|---|
| `SUPERUSER` | Bypasses all permission checks | Grant to no application role. Keep to a minimal number of named admin roles. |
| `CREATEROLE` | Can create roles | Powerful: in PostgreSQL 15 and earlier it can grant itself most non-superuser role privileges. PostgreSQL 16 narrows it to roles the holder administers, but still treat as admin-level. |
| `CREATEDB` | Can create databases | Not needed by application roles. |
| `REPLICATION` | Can start streaming replication / `pg_basebackup` | Give only to dedicated replication roles. |
| `BYPASSRLS` | Skips row-level security | Not for application roles. See [permissions.md](permissions.md#row-level-security). |
| `LOGIN` | May open a connection | Group roles omit it. |
| `CONNECTION LIMIT n` | Caps concurrent connections for the role | A per-role guard rail; size it alongside pool settings (see [05-performance/connection-pooling.md](../05-performance/connection-pooling.md)). |

## Membership and inheritance

A role's effective privileges are its own plus those inherited from
roles it belongs to. In PostgreSQL 16 inheritance is set per
membership: `GRANT app_rw TO app_api WITH INHERIT TRUE` (default for
roles created `INHERIT`) or `WITH INHERIT FALSE` plus `SET ROLE app_rw`
when needed. Before PostgreSQL 16, inheritance was a per-role attribute
(`INHERIT`/`NOINHERIT`). State which behavior you rely on when
documenting a setup.

Privileges for superuser-style attributes (`SUPERUSER`, `CREATEDB`,
`CREATEROLE`, `LOGIN`, `REPLICATION`, `BYPASSRLS`) are never inherited
through membership; they apply only to the role itself.

## Common mistakes

- Connecting the application as `postgres` (the bootstrap superuser).
  A SQL injection or a leaked credential then becomes full cluster
  control, including `COPY ... TO PROGRAM`.
- Sharing one login role across services, so a leak can't be traced or
  revoked individually.
- Running `DROP ROLE` for a role that still owns objects or holds
  privileges: it fails until you run `REASSIGN OWNED BY old_role TO
  new_role;` and `DROP OWNED BY old_role;`. **Both are destructive**
  (`DROP OWNED` revokes privileges and drops objects the role owns).
  Run them only after confirming ownership with `\dt+`/`\dn+` and
  taking a backup.
- Forgetting that roles are cluster-wide: `pg_dump` of one database does
  not include roles; use `pg_dumpall --roles-only` (see
  [07-backups-recovery/pg-dump.md](../07-backups-recovery/pg-dump.md)).

## Security considerations

- Create login roles `NOSUPERUSER NOCREATEDB NOCREATEROLE` explicitly
  so the intent is visible in the script.
- Set per-role timeouts (`statement_timeout`,
  `idle_in_transaction_session_timeout`) with `ALTER ROLE ... SET` so a
  runaway client from this role cannot hold locks indefinitely (see
  [04-transactions/locking.md](../04-transactions/locking.md)).
- Do not put the password in the `CREATE ROLE` statement; see
  [passwords-and-secrets.md](passwords-and-secrets.md).

## Quick revision

- Role = user or group; roles are cluster-wide.
- Login roles for services, `NOLOGIN` group roles to hold privileges.
- No application role is a superuser, ever.
- Clean up with `REASSIGN OWNED` then `DROP OWNED` then `DROP ROLE`, after a backup.
