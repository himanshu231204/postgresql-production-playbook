# pg_restore

## What it is

`pg_restore` is a PostgreSQL client program (Unix shell / CMD /
PowerShell) that restores archives made by `pg_dump` in **custom (`-Fc`),
directory (`-Fd`), or tar (`-Ft`)** format. Plain-format (`-Fp`) dumps are
SQL scripts and are restored with `psql`, not `pg_restore`.

## Why it matters

Restore is the half of the backup that matters during an incident. Its
speed (RTO) depends on parallelism and index builds; its safety depends
on not overwriting the wrong database.

## Syntax

```bash
# Unix shell
pg_restore [connection options] [options] -d TARGET_DB  ARCHIVE
```

Without `-d`, `pg_restore` writes SQL to stdout (use `-f -` to be explicit).

## Example

```bash
# Unix shell (PostgreSQL 16). Restore into a NEW, empty database (safest)
createdb appdb_restore
pg_restore --dbname=appdb_restore --exit-on-error --jobs=4 appdb.dump

# Archive made with `pg_dump -C`: let pg_restore create the database.
# -d names an existing database to connect to first (not the one created).
pg_restore --create --dbname=postgres --exit-on-error appdb.dump

# Plain-format dump: psql, stop at first error, all-or-nothing
psql --set=ON_ERROR_STOP=1 --single-transaction --dbname=appdb_restore --file=appdb.sql

# Refresh planner statistics afterwards (not carried over by a restore)
psql --dbname=appdb_restore --command="ANALYZE"
```

The psql line is a Unix shell invocation of the `psql` client; its
`--command` argument is SQL. Expected result: exit code `0`; `ANALYZE`
prints `ANALYZE`.

## Frequently used flags

| Flag | Effect | Constraint |
|---|---|---|
| `-d`, `--dbname` | Target database | Omit to emit SQL to stdout |
| `-j`, `--jobs=N` | Parallel restore of data and index builds | Custom and directory formats only |
| `-1`, `--single-transaction` | One transaction: all-or-nothing | **Cannot combine with `-j`** (verified on 16.15: `cannot specify both --single-transaction and multiple jobs`) |
| `-e`, `--exit-on-error` | Stop on first SQL error (default is to continue and report a count) | Use in automation |
| `-c`, `--clean` | `DROP` objects before recreating them | **Destructive**, see below |
| `--if-exists` | Use `DROP ... IF EXISTS` with `--clean` | Suppresses errors for objects not present |
| `-C`, `--create` | Create the database first | With `--clean`, drops and recreates the whole database |
| `-l`, `--list` / `-L`, `--use-list=FILE` | Print / restrict by table of contents | Edit the list to skip or reorder items |
| `-n`, `--schema` / `-t`, `--table` | Restore one schema / table | Does not restore dependent objects automatically |
| `-s`, `--schema-only` / `-a`, `--data-only` | Structure only / data only | |
| `--section=pre-data\|data\|post-data` | Run one phase | |
| `-O`, `--no-owner` / `-x`, `--no-privileges` | Skip ownership / GRANTs | Use when roles differ in the target |

## Selective restore

```bash
# Unix shell. 1) List the archive contents
pg_restore --list appdb.dump > toc.txt
# 2) Prefix unwanted lines with ';' (comment), then restore only the rest
pg_restore --use-list=toc.txt --dbname=appdb_restore appdb.dump

# Recover one table into a scratch database, then copy rows back with SQL
pg_restore --dbname=appdb_scratch --schema=public --table=orders appdb.dump
```

## Destructive commands

| Command | What it does | Why risky | Safer alternative | Precaution |
|---|---|---|---|---|
| `pg_restore --clean` / `--clean --create` | Drops existing objects (or the whole database) before recreating | Wipes data written since the backup; wrong `-d` destroys the wrong database | Restore into a new database, verify, then switch the app over or rename | Confirm `-d` and host (`psql -c "\conninfo"` shows the target), take a fresh backup first, stop writers |
| `dropdb` / `DROP DATABASE` (SQL) | Removes the database | Irreversible; fails with active connections | Rename (`ALTER DATABASE ... RENAME TO`, SQL) and keep until verified | Confirm target; terminate sessions only after stopping the app |

`psql -c "\conninfo"` uses a psql meta-command (client-side, not SQL).
`scripts/restore/restore.sh` refuses to overwrite an existing database
unless `REPLACE_EXISTING=1` and `CONFIRM_DB_NAME` match.

## Production usage

- **Never restore over production first.** Restore to a new database or
  host, verify, then cut over. Overwriting is for when production is
  already lost.
- Create roles first: apply `globals.sql` (from `pg_dumpall
  --globals-only`) with `psql` on the target cluster, or the restore
  produces ownership/permission errors.
- Use the same or newer `pg_restore` than the server; restoring into an
  older server major version is unsupported.
- Extensions in the dump (`CREATE EXTENSION vector`) need the extension
  packages installed on the target server first (see
  [10-pgvector/](../10-pgvector/README.md)).
- Time the restore; that figure is your real RTO input.
- Scripted: [scripts/restore/restore.sh](../scripts/restore/restore.sh).

## Common mistakes

- Using `pg_restore` on a plain SQL file (error: input file appears to
  be a text format dump). Use `psql -f`.
- Combining `-1` with `-j`.
- Ignoring errors: default continues past failures, leaving a partial
  database and exit code non-zero. Use `--exit-on-error` and check `$?`.
- `--clean` without `--if-exists` on an empty database prints errors for
  every missing object.
- Forgetting `ANALYZE`; the first queries run on bad plans (see
  [05-performance/analyze.md](../05-performance/analyze.md)).
- Skipping the application-level check: row counts match but sequences
  or permissions are wrong. Run a smoke test.

## Security considerations

- Restoring executes the archive's SQL with the restoring role's
  privileges. Restore only archives you trust; an archive from an
  untrusted source can contain arbitrary SQL.
- Use `--no-owner` plus an explicit role setup instead of restoring as
  superuser everywhere; see [06-security/least-privilege.md](../06-security/least-privilege.md).
- Supply credentials via `PGPASSFILE`/secrets manager, not flags.

## Performance considerations

- `-j` parallelizes table data loading and index/constraint creation;
  gains stop when disk or CPU is saturated. A starting point is the number
  of cores; measure.
- Index builds dominate large restores. For a throwaway scratch restore
  only, temporarily raising `maintenance_work_mem` and relaxing
  durability (`fsync`, `synchronous_commit`, `full_page_writes`) can
  speed it up; never leave these relaxed on a database you keep.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `role "x" does not exist` | Apply `globals.sql` first, or restore with `--no-owner` |
| `could not open extension control file` | Install the extension package on the target server |
| `database "x" already exists` | Restore into a new name, or `--clean --create` deliberately |
| `unsupported version in file header` | `pg_restore` is older than the dump format; use newer client tools |
| `errors ignored on restore: N` | Re-run with `--exit-on-error`; inspect the first error |

## Quick revision

- `pg_restore` for `-Fc/-Fd/-Ft`; `psql` for plain.
- `-j` for speed; `-1` for atomicity; not both.
- Restore into a new database, verify, then switch.
- `--clean` and `DROP DATABASE` are destructive: confirm the target.
- Roles first, `ANALYZE` after.

Back: [pg-dump.md](pg-dump.md). Incident steps:
[15-production-runbooks/restore-database.md](../15-production-runbooks/restore-database.md).
Commands: [16-command-reference/pg-restore.md](../16-command-reference/pg-restore.md).
