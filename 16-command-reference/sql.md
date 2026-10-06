# SQL Quick Reference

PostgreSQL **SQL statements** only — typed in `psql` (or any client) and
ended with `;`. These are not `psql` meta-commands (`\dt`, `\d`, `\copy`:
see [psql.md](psql.md)) and not shell commands. Explanations and tradeoffs
live in [02-sql-fundamentals/](../02-sql-fundamentals/),
[03-database-design/](../03-database-design/),
[04-transactions/](../04-transactions/) and
[05-performance/](../05-performance/); this page is syntax only.

Version: examples run against PostgreSQL 16. Version-specific items are
labeled. Reference: [SQL commands, PG 16](https://www.postgresql.org/docs/16/sql-commands.html).
Example names (`app.orders`, `billing.invoices`, `app_rw`) are fake.

## Destructive statements at a glance

Every statement below is irreversible without a backup or an open
transaction you can still `ROLLBACK`. Confirm the target first
(`SELECT current_database(), current_user;` or `\conninfo`), take a backup
([07-backups-recovery/](../07-backups-recovery/)) and prefer a maintenance
window.

| Statement | What it does | Why risky in production | Safer alternative / precaution |
|---|---|---|---|
| `DROP DATABASE name;` | Deletes the database and all data | Fails while others are connected; `WITH (FORCE)` (PG13+) terminates them | Run `pg_dump` first; check `\l` and connections; rename (`ALTER DATABASE ... RENAME`) and keep it for a retention period |
| `DROP TABLE t;` | Deletes table, data, indexes, triggers | Breaks dependent code; `CASCADE` also drops dependent views/FKs | Omit `CASCADE`; run inside `BEGIN` and inspect; rename to `t_old` first |
| `TRUNCATE t;` | Empties a table instantly | Takes `ACCESS EXCLUSIVE`; not row-by-row, so no `DELETE` triggers; `CASCADE` truncates referencing tables | Use `DELETE ... WHERE` for partial removal; wrap in a transaction (TRUNCATE is transactional) |
| `DELETE FROM t;` (no `WHERE`) or large `DELETE` | Removes rows | Whole table gone; huge deletes bloat the table and hold locks | Always write `WHERE`; `BEGIN; DELETE ...; SELECT count(*) ...;` then `COMMIT`/`ROLLBACK`; batch large deletes |
| `UPDATE t SET ...;` (no `WHERE`) | Rewrites every row | Same as above | Same |
| `VACUUM FULL t;` | Rewrites the table to reclaim disk | `ACCESS EXCLUSIVE` for the whole rewrite; needs spare disk | Plain `VACUUM`; `pg_repack`; only in a window |
| `SELECT pg_terminate_backend(pid);` | Kills a session | Rolls back its transaction, may crash app assumptions | Try `pg_cancel_backend(pid)` first; verify `pid` from `pg_stat_activity` |
| `DROP ROLE r;` / `REVOKE` | Removes login/privileges | Breaks applications | `REASSIGN OWNED BY`, then `DROP OWNED BY`, then `DROP ROLE` |
| `ALTER TABLE ... DROP COLUMN` | Removes a column | Not reversible; old app versions break | Expand/contract migration; see [09-alembic/](../09-alembic/) |

## Databases and roles

| Statement | Purpose | Notes |
|---|---|---|
| `CREATE DATABASE appdb;` | Create a database | Needs `CREATEDB`. Add `TEMPLATE template0 ENCODING 'UTF8'` for a clean one |
| `ALTER DATABASE appdb SET statement_timeout = '30s';` | Per-database default setting | Applies to new sessions |
| `DROP DATABASE IF EXISTS tmpdb WITH (FORCE);` | Drop even with connections | **Destructive** (see table). `WITH (FORCE)` is PG13+ |
| `CREATE ROLE app_rw LOGIN;` | Create a login role | Set the password with `\password app_rw` in psql (hidden prompt), not `PASSWORD '...'` in SQL, which is logged/history-visible. See [06-security/roles.md](../06-security/roles.md) |
| `ALTER ROLE app_rw SET statement_timeout = '15s';` | Per-role default | |
| `ALTER ROLE app_rw CONNECTION LIMIT 20;` | Cap concurrent sessions | |
| `GRANT CONNECT ON DATABASE appdb TO app_rw;` | Allow connecting | |
| `GRANT USAGE ON SCHEMA app TO app_rw;` | Allow using a schema | Needed in addition to table grants |
| `GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app TO app_rw;` | CRUD for the application role | Existing tables only. New tables: `ALTER DEFAULT PRIVILEGES IN SCHEMA app GRANT SELECT ON TABLES TO app_ro;` |
| `REVOKE ALL ON ALL TABLES IN SCHEMA app FROM PUBLIC;` | Remove broad grants | Check with `\dp` / `\ddp` |
| `REASSIGN OWNED BY old_role TO new_role; DROP OWNED BY old_role; DROP ROLE old_role;` | Remove a role safely | Run per database |

Roles split (application CRUD / migrations DDL / admin): [06-security/least-privilege.md](../06-security/least-privilege.md),
[06-security/permissions.md](../06-security/permissions.md).

## Schema and tables

```sql
CREATE SCHEMA IF NOT EXISTS billing;

CREATE TABLE billing.invoices (
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id   bigint NOT NULL REFERENCES app.orders (id) ON DELETE RESTRICT,
  amount     numeric(10,2) NOT NULL CHECK (amount >= 0),
  status     text NOT NULL DEFAULT 'open',
  created_at timestamptz NOT NULL DEFAULT now()
);
```

Expected: `CREATE SCHEMA`, `CREATE TABLE`. Design rules:
[03-database-design/](../03-database-design/).

| Statement | Purpose | Production notes |
|---|---|---|
| `ALTER TABLE billing.invoices ADD COLUMN note text;` | Add a nullable column | Metadata-only, brief `ACCESS EXCLUSIVE`; a volatile `DEFAULT` rewrites the table |
| `ALTER TABLE ... ADD CONSTRAINT c CHECK (...) NOT VALID;` then `ALTER TABLE ... VALIDATE CONSTRAINT c;` | Add a constraint without a long blocking scan | `VALIDATE` takes a weaker lock; the two-step form is the large-table pattern |
| `ALTER TABLE ... RENAME TO / RENAME COLUMN` | Rename | Breaks any client using the old name; see [09-alembic/](../09-alembic/) |
| `ALTER TABLE ... DROP COLUMN c;` | Remove a column | **Destructive**; do after the app stops using it |
| `DROP TABLE IF EXISTS billing.invoices;` | Remove a table | **Destructive** |
| `DROP SCHEMA billing;` | Remove an empty schema | `CASCADE` removes contents: avoid |
| `TRUNCATE billing.invoices RESTART IDENTITY;` | Empty table, reset identity | **Destructive**, `ACCESS EXCLUSIVE` |
| `COMMENT ON TABLE app.orders IS 'customer orders';` | Document an object | Shows in `\d+` |

## Querying and changing data

| Statement | Purpose | Notes |
|---|---|---|
| `SELECT id, amount FROM billing.invoices WHERE status = 'open' ORDER BY created_at DESC LIMIT 10;` | Read rows | Name columns; avoid `SELECT *` in application code |
| `INSERT INTO billing.invoices (order_id, amount) VALUES (1, 10.00), (2, 20.00) RETURNING id;` | Insert and get generated keys | |
| `INSERT ... ON CONFLICT (order_id, status) DO UPDATE SET amount = EXCLUDED.amount;` | Upsert | Needs a unique index/constraint on the conflict target |
| `UPDATE billing.invoices SET status = 'paid' WHERE id = 1 RETURNING id, status;` | Update rows | **Always** `WHERE`; check the row count |
| `DELETE FROM billing.invoices WHERE created_at < now() - interval '90 days';` | Delete rows | See destructive table; batch at scale |
| `MERGE INTO t USING (VALUES (2, 99.00)) AS s(order_id, amount) ON t.order_id = s.order_id WHEN MATCHED THEN UPDATE SET amount = s.amount WHEN NOT MATCHED THEN INSERT (order_id, amount) VALUES (s.order_id, s.amount);` | Conditional upsert | **PG15+** |
| `COPY (SELECT * FROM app.orders) TO '/srv/export/orders.csv' WITH (FORMAT csv, HEADER);` | **Server-side** export | Writes on the server host as the PostgreSQL OS user; needs superuser or `pg_write_server_files`. From a client use psql `\copy` ([psql.md](psql.md)) |

Application code must pass values as bind parameters (driver
placeholders), never format user input into SQL; see
[08-python-fastapi/](../08-python-fastapi/).

## Indexes

| Statement | Purpose | Production notes |
|---|---|---|
| `CREATE INDEX CONCURRENTLY invoices_order_idx ON billing.invoices (order_id);` | Build without blocking writes | Cannot run inside a transaction block (so not with `psql -1`); slower, two scans; a failed build leaves an `INVALID` index to drop |
| `REINDEX INDEX CONCURRENTLY billing.invoices_order_idx;` | Rebuild a bloated/invalid index | PG12+ |
| `DROP INDEX CONCURRENTLY app.orders_customer_idx;` | Drop without blocking | Not in a transaction block |

Index only for a real query pattern (extra storage and slower writes):
[05-performance/indexes.md](../05-performance/indexes.md).

## Transactions

| Statement | Purpose | Notes |
|---|---|---|
| `BEGIN;` / `COMMIT;` / `ROLLBACK;` | Start / finish / abort | Long-open transactions hold locks and block vacuum |
| `BEGIN ISOLATION LEVEL REPEATABLE READ;` | Choose isolation at start | Also `SERIALIZABLE`; default is `READ COMMITTED`. Retry on serialization failure. [04-transactions/isolation-levels.md](../04-transactions/isolation-levels.md) |
| `SAVEPOINT s;` / `ROLLBACK TO SAVEPOINT s;` | Partial rollback | |
| `SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1;` | Claim a row for a worker without blocking | Job-queue pattern; [04-transactions/locking.md](../04-transactions/locking.md) |
| `SET LOCAL lock_timeout = '2s';` | Per-transaction setting | Warns outside a transaction block; use before DDL on busy tables |

## Performance and maintenance

| Statement | Purpose | Notes |
|---|---|---|
| `EXPLAIN SELECT ...;` | Show the plan without running | Safe |
| `EXPLAIN (ANALYZE, BUFFERS) SELECT ...;` | Plan plus real timings and buffer use | **Executes the statement.** For `INSERT/UPDATE/DELETE` wrap in `BEGIN; ... ROLLBACK;`. [05-performance/explain.md](../05-performance/explain.md) |
| `ANALYZE billing.invoices;` | Refresh planner statistics | Cheap; [05-performance/analyze.md](../05-performance/analyze.md) |
| `VACUUM (VERBOSE, ANALYZE) billing.invoices;` | Reclaim dead rows for reuse, update stats | Non-blocking; cannot run in a transaction block. [05-performance/vacuum.md](../05-performance/vacuum.md) |
| `VACUUM FULL billing.invoices;` | Rewrite table | **Destructive to availability** (see table) |

## Settings and diagnostics

| Statement | Purpose | Notes |
|---|---|---|
| `SHOW max_connections;` | Read a setting | |
| `SET statement_timeout = '5s';` / `RESET statement_timeout;` | Session setting | |
| `ALTER SYSTEM SET log_min_duration_statement = '500ms';` then `SELECT pg_reload_conf();` | Persist a setting to `postgresql.auto.conf` and reload | Needs superuser (or `GRANT ALTER SYSTEM`, PG15+). Settings needing restart (`shared_buffers`, `max_connections`) are not applied by reload. Undo: `ALTER SYSTEM RESET name;` |
| `SELECT version();` | Server version | |
| `SELECT current_user, current_database(), inet_server_port();` | Where am I | Put at the top of scripts |
| `SELECT pid, usename, state, wait_event_type, now() - query_start AS runtime FROM pg_stat_activity WHERE datname = current_database() AND pid <> pg_backend_pid() ORDER BY query_start;` | Active sessions | More: [14-observability/pg-stat-activity.md](../14-observability/pg-stat-activity.md) |
| `SELECT pg_cancel_backend(pid);` | Cancel the running query, keep the session | Gentler first step |
| `SELECT pg_terminate_backend(pid);` | End the session | **Destructive** (see table); confirm `pid` and `usename` first |
| `SELECT pg_size_pretty(pg_database_size(current_database()));` | Database size | [14-observability/database-size.md](../14-observability/database-size.md) |
| `SELECT pg_size_pretty(pg_total_relation_size('billing.invoices'));` | Table + indexes + TOAST size | |
| `CREATE EXTENSION IF NOT EXISTS pg_stat_statements;` | Install an extension | `pg_stat_statements` also needs `shared_preload_libraries` (restart), else querying its view errors; managed services have an allow-list |

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `CREATE INDEX CONCURRENTLY cannot run inside a transaction block` | `BEGIN`, `psql -1` or a migration tool's transaction | Run outside a transaction |
| `database "x" is being accessed by other users` | `DROP DATABASE` with sessions open | Stop clients; last resort `WITH (FORCE)` |
| `permission denied for table` | Missing `GRANT` (or no `USAGE` on the schema) | `\dp` to inspect |
| `could not open file ... Permission denied` (COPY) | Server-side `COPY` as the PostgreSQL OS user | Use `\copy` |
| `deadlock detected` / waiting forever | Lock conflict | [04-transactions/deadlocks.md](../04-transactions/deadlocks.md), [15-production-runbooks/lock-contention.md](../15-production-runbooks/lock-contention.md) |

## Quick revision

- Statements end with `;`; meta-commands (`\...`) do not and are not SQL.
- `WHERE` on every `UPDATE`/`DELETE`; verify in a transaction first.
- `CONCURRENTLY` for index build/drop/reindex; not inside a transaction.
- `EXPLAIN ANALYZE` runs the query.
- `pg_cancel_backend` before `pg_terminate_backend`.
