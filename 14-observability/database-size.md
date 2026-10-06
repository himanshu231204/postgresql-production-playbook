# Database, Table, and Index Size

PostgreSQL 16; all queries executed.

## What it is

Size functions (`pg_database_size`, `pg_relation_size`,
`pg_total_relation_size`, `pg_indexes_size`) and `pg_size_pretty()` to
make byte counts readable.

## Why it matters

Unexpected growth is the early warning for a full disk
([../15-production-runbooks/disk-full.md](../15-production-runbooks/disk-full.md)),
and size breakdowns show where bloat, indexes, or TOAST data live
([../05-performance/vacuum.md](../05-performance/vacuum.md)).

## Functions

| Function | Returns |
|---|---|
| `pg_database_size(name)` | Total on-disk size of a database (bytes) |
| `pg_relation_size(regclass)` | One fork of one relation (main heap by default); **excludes** indexes and TOAST |
| `pg_table_size(regclass)` | Heap + TOAST + free space/visibility maps; excludes indexes |
| `pg_indexes_size(regclass)` | All indexes of a table |
| `pg_total_relation_size(regclass)` | Table + TOAST + all indexes |
| `pg_size_pretty(bigint/numeric)` | Human-readable string (`104 kB`) |

## Queries (SQL)

Sizes of all databases:

```sql
SELECT datname, pg_size_pretty(pg_database_size(datname)) AS size
FROM pg_database
WHERE datallowconn
ORDER BY pg_database_size(datname) DESC;
```

`pg_database_size` requires `CONNECT` privilege on the database (or
`pg_read_all_stats` membership); the `datallowconn` filter skips
`template0`.

Largest tables, with a breakdown (run in the database you are inspecting):

```sql
SELECT n.nspname AS schema, c.relname AS "table",
       pg_size_pretty(pg_total_relation_size(c.oid)) AS total,
       pg_size_pretty(pg_relation_size(c.oid))       AS heap,
       pg_size_pretty(pg_indexes_size(c.oid))        AS indexes,
       pg_size_pretty(pg_total_relation_size(c.oid)
                      - pg_relation_size(c.oid)
                      - pg_indexes_size(c.oid))      AS toast_and_other
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm', 'p')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
ORDER BY pg_total_relation_size(c.oid) DESC
LIMIT 20;
```

`relkind`: `r` table, `m` materialized view, `p` partitioned table. For a
partitioned table, `pg_total_relation_size` of the parent covers only the
parent itself; query the partitions (they are `r` rows) for real sizes.

Indexes of one table, by size and usage:

```sql
SELECT s.indexrelname,
       pg_size_pretty(pg_relation_size(s.indexrelid)) AS size,
       s.idx_scan
FROM pg_stat_user_indexes s
WHERE s.relname = 'accounts'          -- replace with your table
ORDER BY pg_relation_size(s.indexrelid) DESC;
```

Per-index never-scanned list: see [slow-queries.md](slow-queries.md).

Combined size of all databases in the cluster (does not include WAL,
logs, or other files outside database directories):

```sql
SELECT pg_size_pretty(sum(pg_database_size(oid))) FROM pg_database WHERE datallowconn;
```

In `psql`, shortcuts (psql meta-commands, not SQL): `\l+` lists
databases with sizes; `\dt+` lists tables with sizes in the current
schema; `\di+` lists indexes with sizes.

## Tracking growth

A single size says little; the **rate** matters. Record
`pg_database_size` and the top tables on a schedule (monitoring system or
a cron job calling [../scripts/diagnostics/pg-diagnostics.sh](../scripts/diagnostics/README.md) `sizes`) and
alert on growth rate and on free disk space, not on a fixed size.

Space outside table sizes that also fills disks: WAL (retained by
inactive replication slots or failing `archive_command` — see
[monitoring.md](monitoring.md)), temporary files (`temp_bytes` in
`pg_stat_database`), and server logs.

## Common mistakes

- Using `pg_relation_size` and concluding a table is small while its indexes and TOAST data are large; use `pg_total_relation_size`.
- Running a "largest tables" query that scans thousands of relations every few seconds.
- Reclaiming space with `VACUUM FULL`: it takes an `ACCESS EXCLUSIVE` lock and rewrites the table, blocking reads and writes for the duration, and needs free disk equal to the new table size. Safer first step: look at why bloat exists (long transactions, autovacuum settings); consider `pg_repack` (extension, must be installed and tested) or a maintenance window with a verified backup.
- Deleting rows and expecting size to drop; ordinary `VACUUM` makes space reusable but rarely returns it to the OS.

## Quick revision

- `pg_total_relation_size` = heap + TOAST + indexes; `pg_relation_size` = heap only.
- Wrap in `pg_size_pretty()`.
- Alert on growth rate and free disk.
- `VACUUM FULL` is exclusive-lock and destructive to availability; avoid on production without a window.
