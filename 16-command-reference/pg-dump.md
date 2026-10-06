# `pg_dump` Flag Reference

`pg_dump` is an **OS-shell client program** (not SQL, not a psql
meta-command). It takes a consistent logical snapshot of **one database**
while the database stays online. Compact flag table: strategy, scheduling,
retention and verification live in
[07-backups-recovery/pg-dump.md](../07-backups-recovery/pg-dump.md) and
[07-backups-recovery/backup-strategy.md](../07-backups-recovery/backup-strategy.md);
restoring is [pg-restore.md](pg-restore.md).

Version: PostgreSQL 16 (`pg_dump --help`, [docs](https://www.postgresql.org/docs/16/app-pgdump.html)).
Connection flags and `PG*` environment variables are the same as
[psql.md](psql.md); put credentials in `~/.pgpass`, never on the command
line ([06-security/passwords-and-secrets.md](../06-security/passwords-and-secrets.md)).

## Common commands

```bash
# Custom format (compressed, selective + parallel restore) — default choice for backups
pg_dump -h HOST -U USER -d DBNAME -Fc -f appdb.dump

# Directory format: the only format that dumps in parallel
pg_dump -h HOST -U USER -d DBNAME -Fd -j 4 -f appdb.dir

# Plain SQL (human-readable; restore with psql)
pg_dump -h HOST -U USER -d DBNAME -f appdb.sql

# Schema only / data only
pg_dump -d DBNAME -s -f schema.sql
pg_dump -d DBNAME -a -Fc -f data.dump

# One schema, one table (names are patterns; quote globs for the shell)
pg_dump -d DBNAME -Fc -n app -f app_schema.dump
pg_dump -d DBNAME -Fc -t app.orders -f orders.dump

# Everything except noisy tables' data (keeps the table definitions)
pg_dump -d DBNAME -Fc --exclude-table-data=app.audit_log -f appdb.dump

# Roles and tablespaces are cluster-wide: pg_dump does NOT include them
pg_dumpall -h HOST -U USER --globals-only -f globals.sql
```

Expected: no output on success (add `-v` for progress on stderr), exit `0`,
and the output file exists. Check it with `pg_restore -l appdb.dump`
(custom/directory/tar). A dump you have not test-restored is not a backup.

## Format (`-F`)

| `-F` | Format | Output | Parallel dump (`-j`) | Restore with | Notes |
|---|---|---|---|---|---|
| `p` (default) | Plain SQL | file / stdout | No | `psql -f` | Readable; no selective restore; no parallel restore |
| `c` | Custom | single file | No | `pg_restore` | Compressed by default; selective and parallel (`pg_restore -j`) restore |
| `d` | Directory | directory | **Yes** | `pg_restore` | One file per table; best for large databases |
| `t` | Tar | tar file | No | `pg_restore` | No compression; 8 GB per-file limit; rarely the right choice |

`-j` with any format except `-Fd` fails: `parallel backup only supported by
the directory format` (verified).

## Flags

| Flag | Purpose | Production notes |
|---|---|---|
| `-d, --dbname` | Database to dump (or last positional argument / `PGDATABASE`) | |
| `-h -p -U -w -W` | Host, port, role, no-prompt, force prompt | Use `-w` in cron |
| `--role=ROLE` | `SET ROLE` before dumping | Dump with a read-only role granted `SELECT`; avoid superuser |
| `-f, --file` | Output file (or directory for `-Fd`) | In PowerShell prefer `-f` over `>` (redirection can re-encode the file); see [windows.md](windows.md) |
| `-F, --format` | `p`, `c`, `d`, `t` | See table |
| `-j, --jobs=N` | Parallel dump workers | Directory format only. Opens N+1 connections and adds load; keep N below idle capacity |
| `-Z, --compress=METHOD[:LEVEL]` | Compression, e.g. `-Z 0`, `-Z 6`, `-Z zstd:3` | Methods `gzip`, `lz4`, `zstd` in PG16+ (if the build supports them); older versions take only a level |
| `-v, --verbose` | Progress on stderr | |
| `-s, --schema-only` | Definitions only | |
| `-a, --data-only` | Data only | Restore needs the schema to exist already |
| `-n / -N` | Include / exclude schema (pattern) | |
| `-t / -T` | Include / exclude table (pattern) | A table dump does not include dependencies you did not select. `--table-and-children` / `--exclude-table-and-children` include partitions (PG16+) |
| `--exclude-table-data=PATTERN` | Dump table definition, skip rows | |
| `--strict-names` | Fail if `-n`/`-t` matches nothing | Use in automation so a typo does not produce an empty "successful" backup |
| `-C, --create` | Add `CREATE DATABASE` to the output | Combine with `-c` only deliberately: it adds `DROP DATABASE` |
| `-c, --clean` | Add `DROP` statements before `CREATE` | **Destructive on restore** (drops existing objects). Add `--if-exists` |
| `--if-exists` | `DROP ... IF EXISTS` with `-c` | |
| `-O, --no-owner` | Omit ownership commands | Restoring into a different role/managed service |
| `-x, --no-privileges` | Omit `GRANT`/`REVOKE` | Re-apply grants deliberately |
| `--no-comments`, `--no-tablespaces`, `--no-publications`, `--no-subscriptions`, `--no-security-labels`, `--no-unlogged-table-data` | Omit those object kinds | Tablespaces rarely exist on the restore target |
| `--inserts`, `--column-inserts`, `--rows-per-insert=N`, `--on-conflict-do-nothing` | Emit `INSERT` instead of `COPY` | Much slower restore; use only for cross-DBMS or partial-conflict loads |
| `--section=pre-data\|data\|post-data` | Dump one section | |
| `--lock-wait-timeout=T` | Fail instead of waiting for a table lock | Avoids a dump queued behind DDL, which in turn blocks other traffic |
| `--serializable-deferrable` | Wait for a safe snapshot | Only matters with serializable workloads |
| `--no-sync` | Skip `fsync` of the output | Faster; the file may be lost on a crash right after |
| `-E, --encoding` | Output encoding | |
| `-b / -B` | Include / exclude large objects | |
| `--enable-row-security` | Dump only rows the role may see (RLS) | A silently partial dump is dangerous; default errors instead |

pg_dump takes `ACCESS SHARE` locks (blocks `ALTER`/`DROP`/`TRUNCATE`
until done) and holds a long-running snapshot, which delays vacuum cleanup
on a busy primary. Run from a replica or off-peak where possible.
Consistency is per database: use `--snapshot` or physical backups
([07-backups-recovery/point-in-time-recovery.md](../07-backups-recovery/point-in-time-recovery.md))
for cross-database consistency or PITR.

## Related server-side tools

| Command (OS shell) | Purpose | Notes |
|---|---|---|
| `pg_dumpall -g -f globals.sql` (`--globals-only`; also `-r` roles only, `-t` tablespaces only) | Roles and tablespaces | The file contains **role password hashes**: treat as a secret |
| `pg_dumpall -f cluster.sql` | Whole cluster as plain SQL | No custom format; no selective restore |
| `pg_basebackup -D DIR -Fp -X stream -P -c fast` | Physical base backup of the whole cluster | Needs a role with `REPLICATION`; basis for PITR. Verify with `pg_verifybackup DIR`. Docs: [07-backups-recovery/point-in-time-recovery.md](../07-backups-recovery/point-in-time-recovery.md) |

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `permission denied for table` | Dump role lacks `SELECT` | Use a role with read access or `pg_read_all_data` (PG14+) |
| `pg_dump: error: aborting because of server version mismatch` | `pg_dump` older than the server | Use a client >= the server major version |
| `parallel backup only supported by the directory format` | `-j` with `-Fc`/`-Fp` | Use `-Fd` |
| Dump hangs | Waiting for a table lock behind DDL/long transaction | `--lock-wait-timeout`; check [14-observability/pg-locks.md](../14-observability/pg-locks.md) |
| Dump is empty / tiny | Pattern matched nothing | `--strict-names` |

## Quick revision

- `pg_dump -Fc -f x.dump -d DB` (restore with `pg_restore`); `-Fd -j N` for parallel.
- `-j` only with `-Fd`. `-C -c` adds `DROP DATABASE`: destructive on restore.
- Roles are not in a `pg_dump`: use `pg_dumpall --globals-only`.
- Use `--strict-names` and `-w` in scripts; test-restore regularly.
