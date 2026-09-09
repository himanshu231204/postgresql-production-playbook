# `pg_dump` Command Reference

Flags and format types for `pg_dump`. For backup strategy, scheduling,
and retention, see [07-backups-recovery/](../07-backups-recovery/).

## Basic syntax

```bash
pg_dump -h HOST -U USER -d DBNAME -F FORMAT -f OUTPUT_FILE
```

`pg_dump` reads the same `PG*` connection environment variables as `psql`
(see [01-postgresql-cli/commands.md](../01-postgresql-cli/commands.md#connection-environment-variables)).

## Format flags (`-F`)

| Format | Flag | Restore with | Notes |
|---|---|---|---|
| Plain SQL | `-F p` (default) | `psql` | Human-readable; a single, large SQL script |
| Custom | `-F c` | `pg_restore` | Compressed by default; supports selective/reordered restore |
| Directory | `-F d` | `pg_restore` | One file per table in a directory; **the only format that supports parallel dump** (`-j`) |
| Tar | `-F t` | `pg_restore` | Similar to custom format but as a `.tar` file |

**Production note:** `-F c` (custom) or `-F d` (directory) are the
practical defaults for anything beyond a small database — both are
compressed and restorable with `pg_restore`'s selective/parallel options.
Plain SQL dumps of a large database are slow to both produce and restore.

## Common flags

| Flag | Purpose | Notes |
|---|---|---|
| `-f file` | Output file (or directory, for `-F d`) | Omit to write to stdout (plain format only) |
| `-j N` / `--jobs=N` | Dump N tables in parallel | Only works with `-F d` (directory format) |
| `-s` / `--schema-only` | Dump schema (DDL) only, no data | |
| `-a` / `--data-only` | Dump data only, no schema | Target tables must already exist to restore into |
| `-t table` | Dump only the named table (repeatable) | Schema-qualify if ambiguous: `-t public.orders` |
| `-n schema` | Dump only the named schema (repeatable) | |
| `-Z 0-9` | Compression level (custom/directory formats) | `0` disables compression |
| `--no-owner` | Omit `ALTER ... OWNER TO` statements | Useful when restoring into a database with different role names |
| `-C` / `--create` | Include a `CREATE DATABASE` statement (plain format) | |
| `-v` | Verbose progress output to stderr | |

## Examples

```bash
# Full backup, custom format (recommended default)
pg_dump -h "$PGHOST" -U "$PGUSER" -d app_db -F c -f app_db.dump

# Parallel backup, directory format
pg_dump -h "$PGHOST" -U "$PGUSER" -d app_db -F d -j 4 -f app_db_dump/

# Schema only — useful for reviewing structure or seeding a new environment
pg_dump -h "$PGHOST" -U "$PGUSER" -d app_db -s -f schema.sql
```

## Common mistakes

- Using plain-format (`-F p`) dumps for a large production database, then
  being surprised restore takes hours with no parallelism available.
- Forgetting `pg_dump` only captures one database — cluster-wide objects
  (roles, tablespaces) require `pg_dumpall -g` (globals only) separately.
- Running a full `pg_dump` against a busy primary during peak traffic
  without considering the read load it adds — dumping is consistent (it
  runs inside one transaction, so it doesn't block writers) but is not
  free of I/O and CPU cost.

## Security considerations

A dump file is a full copy of the data — treat it with the same access
controls as the database itself. Never commit a dump file to version
control, and encrypt it at rest/in transit if it leaves a controlled
environment.
