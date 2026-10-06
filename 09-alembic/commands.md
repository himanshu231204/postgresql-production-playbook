# Alembic Commands

All commands are **Unix shell / Windows CMD / PowerShell** invocations of
the `alembic` CLI (Alembic 1.16). They are not SQL and not `psql`
meta-commands. The CLI is identical on every OS; only the way you set
environment variables differs.

```bash
# Linux / macOS (Unix shell)
export MIGRATION_DATABASE_URL='postgresql+asyncpg://migration_owner:PASSWORD@HOST:5432/appdb'
```

```powershell
# Windows PowerShell
$env:MIGRATION_DATABASE_URL = 'postgresql+asyncpg://migration_owner:PASSWORD@HOST:5432/appdb'
```

```bat
:: Windows CMD
set MIGRATION_DATABASE_URL=postgresql+asyncpg://migration_owner:PASSWORD@HOST:5432/appdb
```

`PASSWORD` and `HOST` are placeholders. Take real values from a secrets
manager (see [06-security/passwords-and-secrets.md](../06-security/passwords-and-secrets.md)).

## Command table

| Command | Purpose | Production notes |
|---|---|---|
| `alembic init alembic` | Create `alembic.ini` and a sync `alembic/` environment | Once per project |
| `alembic init -t async alembic` | Same, with an async `env.py` for asyncpg/`AsyncEngine` | Use when the app uses `postgresql+asyncpg://` |
| `alembic list_templates` | Show templates (`generic`, `async`, `multidb`, `pyproject`, `pyproject_async`) | |
| `alembic revision -m "msg" --rev-id 0008` | Create an empty revision | Hand-written migrations: data moves, `CONCURRENTLY`, constraint steps |
| `alembic revision --autogenerate -m "msg"` | Diff models vs. live DB into a revision | **Review every line**; see [limits](migrations.md#autogenerate-and-what-it-does-not-detect) |
| `alembic upgrade head` | Apply all pending revisions | The deploy command. Fails if there are multiple heads |
| `alembic upgrade +1` / `upgrade 0004` | Apply one step / up to a revision | Prefer explicit target when staging a release |
| `alembic upgrade head --sql` | Print SQL, no DB connection (offline mode) | Hand to a DBA for review; see [production-migrations.md](production-migrations.md#reviewing-the-sql) |
| `alembic downgrade -1` | Run one `downgrade()` | May destroy data; see [rollback-strategies.md](rollback-strategies.md) |
| `alembic downgrade base` | Undo everything | Never on a production database |
| `alembic current` (`-v`) | Revision(s) recorded in the DB | Run first; confirms you target the right database |
| `alembic history` (`-v`, `-i`, `-r 0003:0005`) | List revisions; `-i` marks current/head | Read-only |
| `alembic heads` | Heads in the script directory | CI must show exactly one |
| `alembic branches` | Branch points | Read-only |
| `alembic show 0003` | Print one revision | |
| `alembic check` | Exit non-zero if autogenerate would produce changes | CI drift gate between models and migrations |
| `alembic merge -m "merge" heads` | Create a revision joining multiple heads | Empty merge revision; does not reconcile conflicting changes |
| `alembic stamp 0007` / `stamp head` | Write a revision into `alembic_version` **without running anything** | Repair/adoption only; wrong stamp = silent drift. `--purge` erases the version table first |
| `alembic ensure_version` | Create the version table if missing | |
| `alembic edit <rev>` | Open a revision in `$EDITOR` | |
| `alembic -x key=value upgrade head` | Pass custom args readable from `env.py` via `context.get_x_argument(as_dictionary=True)` | |
| `alembic -c path/to/alembic.ini ...` | Alternate config | Or set `ALEMBIC_CONFIG` |

## Example session

```bash
alembic current                       # expected: previous revision id, e.g. 0006
alembic upgrade head --sql > plan.sql # review the SQL
alembic upgrade head                  # apply
alembic current                       # expected: 0007 (head)
alembic check                         # expected: No new upgrade operations detected.
```

Expected `current` output (verified on Alembic 1.16.5): `0007 (head)`.

## Command-specific cautions

- **`stamp`** changes bookkeeping only. Use it to adopt an existing
  database at the matching revision, or to repair after a manual fix.
  Stamping a revision whose DDL was never applied makes later
  `upgrade` skip it.
- **`downgrade`** runs whatever the `downgrade()` function says. A
  downgrade that drops a column or table is destructive. Back up first.
- **`merge`** only unifies the graph. If two heads both alter the same
  table, review the merged result for conflicts.
- **`upgrade head --sql`** (offline mode) renders SQL without a
  connection. `autocommit_block()` renders as `COMMIT; ...; BEGIN;`.
  Python that needs a live connection (reading `rowcount`, `SELECT`s,
  batch loops) cannot run offline; guard it with
  `op.get_context().as_sql` (the example's `0005` does). Offline output
  is for review; the tested artifact is an online run.

## Quick revision

- `current` before and after; `heads` and `check` in CI.
- `upgrade head` = deploy; `stamp` = bookkeeping only.
- `--sql` for review, not a substitute for a tested run.
