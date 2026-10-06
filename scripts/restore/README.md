# Restore scripts

## What it is

[restore.sh](restore.sh): restores a set produced by
[../backup/backup.sh](../backup/backup.sh) into a PostgreSQL 16 database
with `pg_restore`. Unix shell (bash 4+).

Sequence: verify `SHA256SUMS` -> check the target database -> `createdb`
-> `pg_restore --exit-on-error` (parallel by default) -> `ANALYZE` ->
optional verification query.

## Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `TARGET_DB` | required | Database to create and restore into (simple identifier) |
| `PGHOST`, `PGPORT`, `PGUSER`, `PGSSLMODE`, `PGPASSFILE` | libpq defaults | Connection; no passwords in this script |
| `RESTORE_JOBS` | `4` | Parallel workers |
| `SINGLE_TXN` | `0` | `1` = all-or-nothing (`--single-transaction`); disables parallelism, because the two cannot be combined |
| `NO_OWNER` | `0` | `1` = `--no-owner`, for clusters whose roles differ |
| `REPLACE_EXISTING` | `0` | `1` = drop and recreate an existing `TARGET_DB` (needs `CONFIRM_DB_NAME`) |
| `CONFIRM_DB_NAME` | unset | Must equal `TARGET_DB` for `REPLACE_EXISTING=1` |
| `VERIFY_SQL` | unset | One-value SQL query printed after restore |
| `PG_BIN_DIR` | from `PATH` | Directory containing the PostgreSQL client binaries |

## Usage

```bash
# Unix shell. Restore into a NEW database and check it (default, safe)
export PGHOST=restore-test.internal PGUSER=admin_role
TARGET_DB=appdb_restore_test \
VERIFY_SQL="SELECT count(*) FROM orders" \
  ./scripts/restore/restore.sh /var/backups/postgres/appdb/20261006T021500Z

# Roles first, if the target cluster lacks them (review the file, then apply)
psql --set=ON_ERROR_STOP=1 --dbname=postgres --file=/var/backups/postgres/appdb/20261006T021500Z/globals.sql
```

## Destructive behavior

- **`REPLACE_EXISTING=1` runs `dropdb`** on `TARGET_DB`. Risk: permanent
  loss of everything in that database, including data written after the
  backup. The script demands `CONFIRM_DB_NAME` to match. Precautions:
  verify `PGHOST`/`TARGET_DB`, take a fresh backup of the current
  database, stop application writers (`dropdb` fails while sessions are
  connected), and prefer restoring to a new name then switching over.

## Safety checks

- Refuses to run if a checksum does not match (tested: a modified dump
  is rejected before the target is touched).
- Refuses to touch an existing database without the two-variable
  confirmation.
- `TARGET_DB` is restricted to `[A-Za-z_][A-Za-z0-9_]*`.
- `--exit-on-error`: a failed statement stops the restore with a non-zero
  exit instead of leaving a quietly partial database; a failed run leaves
  the newly created database in place for inspection. Drop it manually.

## Restore testing

Run this on a schedule against the newest backup into a throwaway
database on a non-production instance, time it, and record the result
(see [backup-strategy.md](../../07-backups-recovery/backup-strategy.md)).
Details on flags: [pg-restore.md](../../07-backups-recovery/pg-restore.md).
