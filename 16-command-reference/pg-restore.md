# `pg_restore` Command Reference

Flags for `pg_restore` — used with custom (`-F c`), directory (`-F d`), or
tar (`-F t`) format dumps from [pg_dump](pg-dump.md). A plain SQL dump
(`-F p`) is restored with `psql -f`, not `pg_restore`. For the full
disaster-recovery process, see [07-backups-recovery/](../07-backups-recovery/).

## Basic syntax

```bash
pg_restore -h HOST -U USER -d DBNAME FILE_OR_DIRECTORY
```

The target database (`-d DBNAME`) must already exist — `pg_restore` does
not create it unless the dump was made with `pg_dump -C` and you also pass
`-C` here (in which case connect to `postgres` or another existing
database first, and let `pg_restore -C` issue `CREATE DATABASE` itself).

## Common flags

| Flag | Purpose | Notes |
|---|---|---|
| `-d dbname` | Database to restore into | Must exist unless combined with `-C` |
| `-j N` / `--jobs=N` | Restore N objects in parallel | Requires custom or directory format, and that the dump doesn't need to run inside a single transaction |
| `--clean` | Drop existing objects before recreating them | **Destructive** on the target — combine with `--if-exists` to avoid errors on objects that don't exist yet |
| `--if-exists` | Suppress errors from `--clean` when an object doesn't exist | Use together with `--clean` |
| `-1` / `--single-transaction` | Wrap the whole restore in one transaction | If it fails partway, nothing is left half-applied; cannot be combined with `-j` |
| `-C` / `--create` | Issue `CREATE DATABASE` before restoring | Connect to a different existing database (e.g. `postgres`) when using this |
| `-l` | List the archive's contents (table of contents) without restoring | Use to inspect a dump before restoring, or to build a filtered restore list |
| `-L list-file` | Restore only the items listed in a file produced by `-l` | For selective/partial restores |
| `-t table` | Restore only the named table (repeatable) | |
| `-n schema` | Restore only the named schema (repeatable) | |
| `--no-owner` | Skip restoring object ownership | Matches `pg_dump --no-owner`, useful across environments with different roles |
| `-v` | Verbose progress output to stderr | |

## Examples

```bash
# Inspect what's in a dump before touching anything
pg_restore -l app_db.dump

# Restore into an existing, empty database
pg_restore -h "$PGHOST" -U "$PGUSER" -d app_db app_db.dump

# Restore destructively into a database that already has (stale) objects
pg_restore -h "$PGHOST" -U "$PGUSER" -d app_db --clean --if-exists app_db.dump

# Parallel restore from a directory-format dump
pg_restore -h "$PGHOST" -U "$PGUSER" -d app_db -j 4 app_db_dump/
```

## Common mistakes

- Running `--clean` against a production database that wasn't the
  intended target — it drops existing objects first. Always confirm
  `-d`/`-h` before adding `--clean`.
- Trying to combine `-j` (parallel) with `-1` (single transaction) — they
  are mutually exclusive.
- Assuming `pg_restore` works on a plain SQL dump — it doesn't; use
  `psql -f dump.sql` for `-F p` dumps.

## Production considerations

- `--clean --if-exists` is the standard pattern for restoring over an
  existing (possibly stale) schema, but it is destructive by design —
  never run it against a database you're not certain you mean to
  overwrite. See [AGENTS.md](../AGENTS.md#18-production-safety-in-content)
  for how this repository flags destructive operations.
- For a full production restore/recovery drill, follow
  [15-production-runbooks/restore-database.md](../15-production-runbooks/restore-database.md).
