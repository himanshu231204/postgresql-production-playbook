# `pg_restore` Flag Reference

`pg_restore` is an **OS-shell client program** that restores archives made
by `pg_dump` in **custom (`-Fc`), directory (`-Fd`) or tar (`-Ft`)** format.
It is not SQL and not a psql meta-command. A **plain-SQL** dump (`-Fp`) is
not accepted: restore it with `psql -X -v ON_ERROR_STOP=1 -d DBNAME -f file.sql`
([psql.md](psql.md)).

Compact flag table. The disaster-recovery procedure, verification and
sequencing are in
[07-backups-recovery/pg-restore.md](../07-backups-recovery/pg-restore.md),
[07-backups-recovery/disaster-recovery.md](../07-backups-recovery/disaster-recovery.md) and
[15-production-runbooks/restore-database.md](../15-production-runbooks/restore-database.md).
Dumping: [pg-dump.md](pg-dump.md).

Version: PostgreSQL 16 (`pg_restore --help`, [docs](https://www.postgresql.org/docs/16/app-pgrestore.html)).
Credentials via `~/.pgpass`, not the command line
([06-security/passwords-and-secrets.md](../06-security/passwords-and-secrets.md)).

## Common commands

```bash
# 1. Inspect the archive without touching any database
pg_restore -l appdb.dump

# 2. Restore into a NEW, empty database (the safe default)
createdb -h HOST -U USER appdb_restore
pg_restore -h HOST -U USER -d appdb_restore --no-owner --no-privileges -j 4 -v appdb.dump

# 3. All-or-nothing, stop at first error (cannot be combined with -j)
pg_restore -d appdb_restore -1 -e appdb.dump

# 4. Let the archive create the database (connect to a maintenance DB first)
pg_restore -h HOST -U USER -d postgres -C appdb.dump

# 5. One table's data into an existing table (schema must already exist)
pg_restore -d appdb_restore -a -n app -t orders appdb.dump

# 6. Generate SQL instead of restoring (review before applying)
pg_restore -f - -s appdb.dump | less
```

Expected for #2: nothing on stdout without `-v`; exit `0`. Verify with
`psql -d appdb_restore -c "SELECT count(*) FROM app.orders;"` and compare
counts to the source. With errors ignored, `pg_restore` prints
`warning: errors ignored on restore: N` and exits `1` (observed): do not treat
that as success without reading the errors, since a re-run into a populated
database produces such errors by design.

## Flags

| Flag | Purpose | Production notes |
|---|---|---|
| `-d, --dbname` | Database to restore into | Without `-d`, SQL goes to stdout (same as `-f -`) |
| `-h -p -U -w -W`, `--role=ROLE` | Connection, `SET ROLE` | `-w` in automation |
| `-f, --file` | Write the generated SQL to a file (`-` = stdout) | Dry run / review |
| `-F, --format` | `c`, `d`, `t` | Usually auto-detected |
| `-l, --list` | Print the archive's table of contents | Read-only, safe |
| `-L, --use-list=FILE` | Restore only/ordered by a (edited) TOC list | `pg_restore -l x.dump > toc.list`, delete or `;`-comment lines, then `-L toc.list` |
| `-j, --jobs=N` | Parallel restore | Custom and directory formats. Incompatible with `-1` (`cannot specify both --single-transaction and multiple jobs`, verified). Heavy I/O and index builds: size N to the target |
| `-1, --single-transaction` | One transaction for the whole restore | A single error rolls back everything. Use with `-e`; no parallelism |
| `-e, --exit-on-error` | Stop on first error | Default is to **continue** after errors |
| `-v, --verbose` | Progress | |
| `-s, --schema-only` / `-a, --data-only` | Definitions only / rows only | Data-only needs the tables to exist; `--disable-triggers` (needs superuser) avoids FK-order failures |
| `-n / -N SCHEMA` | Restore only / exclude a schema | |
| `-t TABLE` | Restore one table (also views, sequences) | Restores only that object, not its schema: `CREATE SCHEMA app;` must already exist (verified: errors otherwise) |
| `-I`, `-P`, `-T` | Restore one index / function / trigger | |
| `--section=pre-data\|data\|post-data` | Restore one phase | Pre-data, then data, then indexes/constraints (post-data) |
| `-O, --no-owner` / `-x, --no-privileges` | Skip ownership / `GRANT`s | Needed when the target roles differ or on managed services; re-apply grants deliberately |
| `-S, --superuser=NAME` | Superuser for `--disable-triggers` | |
| `-C, --create` | Create the database from the archive | Connect with `-d` to an existing database (e.g. `postgres`); objects go into the new one |
| `-c, --clean` | `DROP` objects before recreating | **Destructive**: see below. Pair with `--if-exists` |
| `--if-exists` | `DROP ... IF EXISTS` (with `-c`) | Avoids spurious errors on an empty target |
| `--no-data-for-failed-tables` | Skip rows if the table could not be created | |
| `--no-comments`, `--no-tablespaces`, `--no-publications`, `--no-subscriptions`, `--no-security-labels` | Skip those object kinds | Dropping subscriptions/publications avoids a restored copy connecting to production replication |

## Destructive options

| Option | What it does | Why risky | Safer alternative / precaution |
|---|---|---|---|
| `--clean` / `-c` | Drops every object in the archive from the target before recreating | Replaces live data; wrong `-d` = data loss | Restore into a new database (`createdb`), validate, then switch the application over or rename |
| `-C` with `-c` | Drops and recreates the **whole database** (verified: `pg_restore -C -d postgres -c --if-exists` recreated the database) | Disconnects/destroys the existing database | Take a fresh `pg_dump` of the target first; confirm `\l` and `\conninfo`; maintenance window |
| `-a` into a populated table | Inserts rows into existing data | Duplicates or constraint errors; with `--disable-triggers`, skips FK checks | Truncate deliberately in a transaction, or restore into an empty database |
| Running without `-1`/`-e` | Continues after errors | Half-restored database that looks complete | Add `-e`, or `-1`; read the full error list |

Before any restore against a non-empty target: confirm the host and
database name, take a backup of what is there, stop or drain writers, and
rehearse the exact command on a scratch database first.

## Typical restore sequence (version and order)

1. `pg_restore -l` the archive; check "Dumped by pg_dump version" in the header.
2. Use a `pg_restore` at least as new as the dump's `pg_dump`; the server
   can be the same or newer major version (not older).
3. Restore roles first (`psql -f globals.sql`, from
   `pg_dumpall --globals-only`) or use `--no-owner`.
4. Restore, then `ANALYZE` the new database (statistics are not restored).
5. Validate counts, constraints and extensions (`\dx`).

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `schema "app" already exists` / `relation ... already exists` | Target not empty | Restore into a fresh database or use `--clean --if-exists` knowingly |
| `role "x" does not exist` | Ownership/grants reference missing roles | Create roles first or `--no-owner --no-privileges` |
| `unsupported version (1.15) in file header` | `pg_restore` older than the `pg_dump` that wrote it | Use a newer `pg_restore` |
| `input file appears to be a text format dump` | Plain SQL dump | Use `psql -f` |
| `could not execute query: ERROR: extension "x" is not available` | Extension package missing on target | Install it, then restore |
| Restore is very slow | Single-threaded, or plain format | `-j` with `-Fc`/`-Fd`; see [05-performance/](../05-performance/) for index/maintenance settings |

## Quick revision

- Safe default: `createdb new; pg_restore -d new --no-owner -j 4 file.dump`.
- `-l` to inspect, `-L` to select, `-f -` to preview SQL.
- `-1` and `-j` are mutually exclusive; default continues past errors, `-e` stops.
- `--clean` and `-C -c` destroy existing data: never the first option on production.
- Plain `.sql` dumps restore with `psql`, not `pg_restore`.
