# Backup scripts

## What it is

[backup.sh](backup.sh): a logical backup of one PostgreSQL 16 database
using `pg_dump`, plus cluster roles/tablespaces via `pg_dumpall
--globals-only`. Unix shell (bash 4+); on Windows run it under WSL or
Git Bash, or translate the commands for PowerShell.

Each run writes one self-contained, timestamped set:

```text
$BACKUP_DIR/<db>/<UTC timestamp>/
  <db>.dump | <db>.dir/   pg_dump archive (custom or directory format)
  globals.sql             roles and tablespaces
  toc.txt                 pg_restore --list output (proves the archive parses)
  SHA256SUMS              checksums of every file in the set
```

The set is built in a hidden `.incomplete-*` directory and renamed only
on success, so an interrupted run never leaves something that looks like
a good backup.

## Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `PGDATABASE` | required | Database to dump |
| `PGHOST`, `PGPORT`, `PGUSER`, `PGSSLMODE` | libpq defaults | Connection; use `PGSSLMODE=verify-full` for remote servers |
| `PGPASSFILE` | `~/.pgpass` | Password source; never put passwords in the script or env files committed to git |
| `BACKUP_DIR` | `./backups` | Output root |
| `BACKUP_FORMAT` | `custom` | `custom` (single file) or `directory` (enables `-j`) |
| `DUMP_JOBS` | `4` | Parallel workers, directory format only |
| `DUMP_GLOBALS` | `1` | Set `0` where `pg_dumpall --globals-only` is not permitted (some managed services) |
| `RETENTION_DAYS` | `7` | Delete sets older than N days under `$BACKUP_DIR/<db>`; `0` disables |
| `PG_BIN_DIR` | from `PATH` | Directory containing the PostgreSQL client binaries |

## Usage

```bash
# Unix shell
export PGHOST=db.internal PGUSER=backup_role PGSSLMODE=verify-full
PGDATABASE=appdb BACKUP_DIR=/var/backups/postgres ./scripts/backup/backup.sh

# Cron, nightly at 02:15 (crontab entry)
# 15 2 * * * PGDATABASE=appdb BACKUP_DIR=/var/backups/postgres /opt/pg/backup.sh >> /var/log/pg-backup.log 2>&1
```

The script prints the backup set path on stdout; logs go to stderr.
Exit code is non-zero on any failure (`set -euo pipefail`), so
schedulers and monitoring can alert on it.

## Destructive behavior

- **Retention pruning** runs `rm -rf` on completed sets older than
  `RETENTION_DAYS` inside `$BACKUP_DIR/$PGDATABASE` only (names must match
  the timestamp pattern). Risk: a wrong `BACKUP_DIR` or a too-small
  value deletes real backups. Precaution: run with `RETENTION_DAYS=0`
  first; keep off-site copies independent of this pruning.

## What it does not do

- It does not encrypt, upload off-host, or protect against loss of the
  host. Add encryption and a copy to separate storage (see
  [backup-strategy.md](../../07-backups-recovery/backup-strategy.md)).
- It is logical only: no point-in-time recovery. For that, see
  [point-in-time-recovery.md](../../07-backups-recovery/point-in-time-recovery.md).
- Roles in `globals.sql` include password hashes when the dumping role
  can read them. The files are created with mode `0600`/`0700`; still
  encrypt and restrict them.

## Restore

[scripts/restore/restore.sh](../restore/restore.sh). Details:
[pg-dump.md](../../07-backups-recovery/pg-dump.md).
