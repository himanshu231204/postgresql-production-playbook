# pg_dump

## What it is

`pg_dump` is a PostgreSQL client program (Unix shell / Windows CMD /
PowerShell: the same flags on every platform) that writes a logical
backup of **one database**. It is not SQL and not a psql meta-command.
`pg_dumpall` dumps a whole cluster, and is used here only for roles and
tablespaces.

## Why it matters

It is the portable backup: restorable into a newer major version,
selectable per table/schema, and consistent (one snapshot) while the
database stays online. It does not give point-in-time recovery (see
[point-in-time-recovery.md](point-in-time-recovery.md)).

## Syntax

```bash
# Unix shell. Connection via libpq env vars or flags; password via PGPASSFILE.
pg_dump [connection options] [options] dbname
```

## Output formats

| `-F` | Format | Restore with | Parallel dump (`-j`) | Parallel restore | Notes |
|---|---|---|---|---|---|
| `p` (default) | Plain SQL script | `psql -f` | No | No | Human-readable; no selective restore |
| `c` | Custom archive | `pg_restore` | **No** | Yes (`-j`) | Compressed by default; selective restore; single file |
| `d` | Directory | `pg_restore` | **Yes** | Yes (`-j`) | One file per table; the only format `pg_dump -j` accepts |
| `t` | Tar | `pg_restore` | No | No | Uncompressed; per-file size limit; rarely the right choice |

`pg_dump -Fc -j 4 ...` fails with `parallel backup only supported by
the directory format` (verified on 16.15). Use `-Fd` for parallel dumps.

## Example

```bash
# Unix shell. Custom format, single file (PostgreSQL 16)
pg_dump --format=custom --file=appdb.dump appdb

# Directory format, 4 parallel workers
pg_dump --format=directory --jobs=4 --file=appdb.dir appdb

# Compression method (PostgreSQL 16+: gzip, lz4, zstd). Check support with
# `pg_dump -Fc -Z zstd:3 ...`; it errors if the build lacks the library.
pg_dump --format=custom --compress=zstd:3 --file=appdb.dump appdb

# Plain SQL, schema only (for review or diffing)
pg_dump --schema-only --file=appdb-schema.sql appdb

# Roles and tablespaces, which pg_dump does not include
pg_dumpall --globals-only --file=globals.sql          # roles + tablespaces
pg_dumpall --roles-only --file=roles.sql              # roles only
```

Expected result: the output file or directory exists; exit code `0`.
Confirm the archive is readable:

```bash
pg_restore --list appdb.dump | head      # prints the table of contents
```

## Frequently used flags

| Flag | Effect |
|---|---|
| `-f`, `--file` | Output file (or directory for `-Fd`) |
| `-j`, `--jobs=N` | Parallel workers (directory format only); each uses a connection |
| `-Z`, `--compress=METHOD[:DETAIL]` | Compression; `-Z 0` disables |
| `-s`, `--schema-only` / `-a`, `--data-only` | Split structure from data |
| `-t`, `--table=PATTERN` / `-T`, `--exclude-table` | Include / exclude tables |
| `-n`, `--schema=PATTERN` / `-N`, `--exclude-schema` | Include / exclude schemas |
| `--exclude-table-data=PATTERN` | Keep a table's definition, skip its rows (logs, caches) |
| `-O`, `--no-owner` / `-x`, `--no-privileges` | Omit ownership / GRANTs (restore into a cluster with different roles) |
| `-C`, `--create` | Include `CREATE DATABASE` (plain) or record it (archive; used with `pg_restore --create`) |
| `--section=pre-data\|data\|post-data` | Dump one phase |
| `--serializable-deferrable` | Wait for a snapshot guaranteed anomaly-free (only matters for serializable workloads) |

`pg_dumpall`: `-g`/`--globals-only`, `-r`/`--roles-only`,
`--no-role-passwords` (omit password hashes; use when the dump file's
confidentiality cannot be guaranteed).

## Production usage

- Run as a dedicated backup role with read access to all data. On
  PostgreSQL 14+ the predefined role `pg_read_all_data` grants that
  without superuser. See [06-security/least-privilege.md](../06-security/least-privilege.md).
- Dump from a standby when you have one, to keep load and long
  snapshots off the primary. A dump on a hot standby can be canceled by
  replication conflicts; see `max_standby_streaming_delay` and
  `hot_standby_feedback` in the PostgreSQL docs and the tradeoffs.
- Write to a temporary name and rename on success so a half-written dump
  is never mistaken for a good one; checksum it; encrypt before upload
  (see [backup-strategy.md](backup-strategy.md)).
- `pg_dump` takes `ACCESS SHARE` locks on every table it dumps, which
  block only `ACCESS EXCLUSIVE` operations (`ALTER TABLE`, `DROP`,
  `TRUNCATE`, `VACUUM FULL`). A long dump can therefore stall a
  migration, and a queued migration then blocks other queries behind it.
  Schedule dumps away from deploys (see
  [04-transactions/locking.md](../04-transactions/locking.md)).
- Ready-made script: [scripts/backup/backup.sh](../scripts/backup/backup.sh).

## Common mistakes

- Assuming the dump contains roles. It does not; restore fails with
  `role "x" does not exist` or silently changes ownership. Dump globals too.
- Using `-j` with `-Fc`.
- Using a `pg_dump` older than the server. Use the same or newer major
  version.
- Passing the password on the command line or in a script. Use
  `PGPASSFILE` or a secrets manager.
- Redirecting a plain dump through a pipe and ignoring failures. Use
  `set -o pipefail` in shell scripts.
- Never restoring the result (see [backup-strategy.md](backup-strategy.md)).

## Security considerations

- Dump files contain all data; `pg_dumpall` output includes role password
  hashes. Write with `umask 077`, encrypt, and keep them out of git.
- Bad vs. good:

```bash
# BAD: password visible in shell history and process list
PGPASSWORD=hunter2 pg_dump -h db.internal -U backup appdb > appdb.sql

# GOOD: credentials from ~/.pgpass (mode 0600) or a secrets manager;
# TLS verified
PGSSLMODE=verify-full pg_dump -h db.internal -U backup_role --format=custom -f appdb.dump appdb
```

## Performance considerations

- Custom/directory formats compress by default; compression costs CPU
  on the machine running `pg_dump`. Lower the level or use `lz4` (16+)
  when CPU-bound.
- `-j` speeds up dumps of many large tables, but not one huge table, and
  adds concurrent load on the server.
- A long-running snapshot holds back vacuum cleanup on the source.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `server version mismatch` abort | Client older than server; install matching/newer client tools |
| `permission denied for table` | Backup role lacks `SELECT`; grant `pg_read_all_data` (PG 14+) |
| `parallel backup only supported by the directory format` | Use `-Fd` with `-j` |
| Dump hangs | Waiting on `ACCESS SHARE` behind a queued `ACCESS EXCLUSIVE`; inspect `pg_locks` ([14-observability/pg-locks.md](../14-observability/pg-locks.md)) |
| `canceling statement due to conflict with recovery` (on standby) | Replication conflict; dump from primary, or tune standby delay settings |

## Quick revision

- One database per `pg_dump`; roles via `pg_dumpall --globals-only`.
- `-Fc` single file; `-Fd` is the only parallel-dump format.
- Verify with `pg_restore --list`; actually restore to prove it.
- Same or newer client than server; credentials via `PGPASSFILE`.

Next: [pg-restore.md](pg-restore.md). Commands:
[16-command-reference/pg-dump.md](../16-command-reference/pg-dump.md).
