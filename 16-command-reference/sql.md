# SQL Statement Quick Reference

A flat lookup table of core PostgreSQL SQL statements — syntax and
one-line purpose only. For full explanations, tradeoffs, and examples,
see [02-sql-fundamentals/](../02-sql-fundamentals/) (queries),
[03-database-design/](../03-database-design/) (schema/DDL), and
[04-transactions/](../04-transactions/) (transaction control) once those
pages are written.

**Reminder:** these are SQL statements, sent to and executed by the
server. They are not the same thing as `psql` meta-commands (`\dt`, `\d`,
...) — see [01-postgresql-cli/commands.md](../01-postgresql-cli/commands.md)
for those.

## Data definition (DDL)

| Statement | Syntax | Purpose |
|---|---|---|
| `CREATE DATABASE` | `CREATE DATABASE name;` | Create a new database |
| `CREATE SCHEMA` | `CREATE SCHEMA name;` | Create a namespace for tables/views within a database |
| `CREATE TABLE` | `CREATE TABLE name (col type [constraints], ...);` | Create a table |
| `ALTER TABLE` | `ALTER TABLE name ADD COLUMN col type;` (or `DROP COLUMN`, `ALTER COLUMN ... TYPE`, `ADD CONSTRAINT`, ...) | Modify an existing table's structure |
| `DROP TABLE` | `DROP TABLE name;` | **Destructive** — deletes the table and all its data; see [AGENTS.md](../AGENTS.md#18-production-safety-in-content) production-safety rules |
| `CREATE INDEX` | `CREATE INDEX name ON table (col);` | Add an index; use `CREATE INDEX CONCURRENTLY` in production to avoid a blocking table lock |
| `DROP INDEX` | `DROP INDEX name;` | Remove an index; use `DROP INDEX CONCURRENTLY` in production |
| `CREATE ROLE` / `CREATE USER` | `CREATE ROLE name WITH LOGIN PASSWORD '...';` | Create a role (`CREATE USER` is `CREATE ROLE ... LOGIN` by default) |

## Data manipulation (DML)

| Statement | Syntax | Purpose |
|---|---|---|
| `SELECT` | `SELECT col, ... FROM table WHERE ...;` | Query rows |
| `INSERT` | `INSERT INTO table (col, ...) VALUES (...);` | Add rows |
| `UPDATE` | `UPDATE table SET col = value WHERE ...;` | Modify existing rows — **always include `WHERE`** unless you mean every row |
| `DELETE` | `DELETE FROM table WHERE ...;` | **Destructive** — remove rows; always include `WHERE` unless you mean every row |
| `UPSERT` | `INSERT INTO table (...) VALUES (...) ON CONFLICT (col) DO UPDATE SET ...;` | Insert, or update on a conflicting unique/primary key |
| `TRUNCATE` | `TRUNCATE TABLE name;` | **Destructive** — removes all rows fast, without per-row logging; cannot be filtered with `WHERE` |

## Query building blocks

| Clause | Syntax | Purpose |
|---|---|---|
| `JOIN` | `SELECT ... FROM a JOIN b ON a.id = b.a_id;` | Combine rows from two tables (also `LEFT JOIN`, `RIGHT JOIN`, `FULL JOIN`) |
| `GROUP BY` | `SELECT col, count(*) FROM table GROUP BY col;` | Aggregate rows sharing a value |
| `ORDER BY` | `SELECT ... ORDER BY col [ASC\|DESC];` | Sort results |
| `CTE` | `WITH name AS (SELECT ...) SELECT * FROM name;` | Name a subquery for readability/reuse within one statement |

## Access control

| Statement | Syntax | Purpose |
|---|---|---|
| `GRANT` | `GRANT SELECT, INSERT ON table TO role;` | Give a role a privilege |
| `REVOKE` | `REVOKE INSERT ON table FROM role;` | Remove a privilege |

## Transaction control

| Statement | Syntax | Purpose |
|---|---|---|
| `BEGIN` | `BEGIN;` | Start an explicit transaction |
| `COMMIT` | `COMMIT;` | Persist the transaction's changes |
| `ROLLBACK` | `ROLLBACK;` | Discard the transaction's changes |
| `SAVEPOINT` | `SAVEPOINT name;` | Mark a point to roll back to within a transaction, without discarding everything |
| `ROLLBACK TO SAVEPOINT` | `ROLLBACK TO SAVEPOINT name;` | Undo back to a savepoint, keeping the transaction open |

## Diagnostics (run as SQL, not meta-commands)

| Statement | Syntax | Purpose |
|---|---|---|
| `EXPLAIN` | `EXPLAIN SELECT ...;` | Show the planned query execution plan without running it |
| `EXPLAIN ANALYZE` | `EXPLAIN ANALYZE SELECT ...;` | Run the query and show the actual plan with real timings — see [05-performance/explain.md](../05-performance/explain.md) |
| `ANALYZE` | `ANALYZE table;` | Refresh the planner's statistics for a table |
| `VACUUM` | `VACUUM table;` | Reclaim space from dead rows |
| `VACUUM FULL` | `VACUUM FULL table;` | **Destructive/blocking** — rewrites the whole table and takes an exclusive lock; see [AGENTS.md](../AGENTS.md#18-production-safety-in-content) production-safety rules |

## Common mistakes

- Running `UPDATE`/`DELETE` without a `WHERE` clause against a production
  table.
- Reaching for `TRUNCATE` when a filtered `DELETE` was actually needed —
  `TRUNCATE` cannot target a subset of rows.
- Using plain `DROP INDEX`/`CREATE INDEX` (not the `CONCURRENTLY` variant)
  on a production table, taking a lock that blocks writes.
