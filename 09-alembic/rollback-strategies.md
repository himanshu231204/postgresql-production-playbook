# Rollback Strategies

Alembic 1.16, PostgreSQL 16. Behavior marked "verified" was run against a
PostgreSQL 16 test database with the example project in
[examples/alembic-postgres/](../examples/alembic-postgres/README.md).

## What it is

Deciding how to undo or move past a schema change that is wrong, failed,
or incompatible with the application: run `alembic downgrade`, or write a
new forward migration (roll-forward).

## Why it matters

A downgrade is code that is rarely tested, runs under pressure, takes the
same locks as the upgrade, and cannot restore data a migration deleted.
Plan the rollback before the upgrade ships.

## Downgrade vs roll-forward

| | `alembic downgrade -1` | Roll-forward (new revision) |
|---|---|---|
| Best for | Additive changes not yet depended on (new empty column, new index) | Anything with data written since, or already running in production |
| Risk | Takes the same locks; may drop data; revision history diverges from what other environments applied | A fix must be written, reviewed, and deployed under time pressure |
| History | Moves `alembic_version` back | Linear, auditable |
| Tradeoff | Fast to type, easy to get wrong | Slower, safer, repeatable across environments |

Neither is universally right. Default for production: roll forward with
a small corrective revision, and keep `downgrade()` for development,
CI, and the narrow additive cases below. Revert the **application** first
(redeploy the previous release): expand-phase schemas are compatible with
the old app, which is why additive-first matters.

## Which operations are reversible

| Upgrade operation | Downgrade | Data loss? |
|---|---|---|
| `CREATE TABLE` | `DROP TABLE` | **Yes**, all rows written since |
| `ADD COLUMN` | `DROP COLUMN` | **Yes**, values written to it |
| `CREATE INDEX` | `DROP INDEX` | No (rebuildable) |
| `ADD CONSTRAINT` | `DROP CONSTRAINT` | No |
| `SET NOT NULL` | `DROP NOT NULL` | No |
| Batched backfill | Nothing to undo (no-op) | No |
| `DROP COLUMN` / `DROP TABLE` | Re-create structure only | **Irreversible**: data is gone; only a backup restores it |
| `ALTER COLUMN TYPE` (narrowing/lossy) | Cast back | Possible precision loss |
| Data migrations that overwrite or delete | Rarely invertible | Usually yes |

Migrations that can only be fixed forward: any drop, lossy type change,
destructive data update, and anything after which the application wrote
data that the old schema cannot store. In those revisions, write the
`downgrade()` honestly: either raise an exception
(`raise NotImplementedError("irreversible; restore from backup")`) or
document that it re-creates structure only. The example's
[0007](../examples/alembic-postgres/alembic/versions/0007_contract_drop_users_name.py)
downgrade re-creates `name` and repopulates it from `full_name`, which is
lossless only because the columns were kept identical.

**Destructive: `alembic downgrade`.** What it does: runs each
`downgrade()` from the current revision down. Why risky: may drop columns
or tables. Safer alternative: roll forward, or restore a backup. Before
running: verified backup, `alembic current`, confirm the target
environment, test on a copy.

## A migration failed mid-way

Because PostgreSQL DDL is transactional, an ordinary failed
`alembic upgrade` rolls back **all** pending revisions in that run and
leaves `alembic_version` unchanged (verified: a run with
`lock_timeout` firing on `DROP COLUMN` left `alembic current` at the
previous revision and the column intact). Steps:

1. `alembic current` and `alembic heads`: confirm what is recorded.
2. Read the error. Common: lock timeout (retry later), constraint
   violation (fix data), permission (wrong role).
3. Check for leftovers that transactions cannot roll back:
   - `INVALID` indexes from a failed `CONCURRENTLY` build:
     ```sql
     -- PostgreSQL SQL
     SELECT indexrelid::regclass FROM pg_index WHERE NOT indisvalid;
     DROP INDEX CONCURRENTLY IF EXISTS app.ix_orders_user_id_created_at;
     ```
   - Committed batches from an `autocommit_block()` (backfills are
     idempotent by design: re-run).
4. Fix forward and re-run `alembic upgrade head`.

Exception: a revision that used `autocommit_block()` is **not** atomic.
Work before the block was committed, so the database can be at a state
between revisions, with `alembic_version` still at the older id. Keep such
revisions to a single concern so re-running is safe. Full incident
procedure: [15-production-runbooks/failed-migration.md](../15-production-runbooks/failed-migration.md).

### A migration is hanging

If the migration is waiting on a lock and the app is stalling, cancel it
first. **`pg_terminate_backend`** terminates a session (destructive for
that session; rolls back its open transaction). Prefer
`pg_cancel_backend(pid)` (cancels the current query only):

```sql
-- PostgreSQL SQL. Identify the migration by application_name set in env.py.
SELECT pid, state, wait_event_type, now() - xact_start AS xact_age, left(query, 80)
FROM pg_stat_activity WHERE application_name = 'alembic';

SELECT pg_cancel_backend(<pid>);       -- try this first
-- SELECT pg_terminate_backend(<pid>); -- only if cancel does not work; confirm the pid first
```

Cancelling a transactional migration rolls it back; cancelling a
`CREATE INDEX CONCURRENTLY` leaves an `INVALID` index to drop.
See [14-observability/pg-stat-activity.md](../14-observability/pg-stat-activity.md).

## Editing an applied migration

Do not edit a migration that has already been applied in any shared or
production environment. The file and the database then disagree: Alembic
does not re-run an applied revision, so the edit never takes effect there,
while new environments get the edited version. Schema **drift** between
environments follows silently, and `alembic check` will not tell you.
Instead add a new revision that corrects the schema.

Acceptable only when the revision was never applied anywhere beyond your
own local database (rebuild it: `downgrade` or recreate, then `upgrade`),
or when a failed revision was fully rolled back (verify with
`alembic current`) and never reached a shared environment. If a hand edit
of an applied revision is truly unavoidable (for example removing a
non-working `downgrade()`), state it in the PR and reconcile every
environment's actual schema against the file.

## `stamp` is not a rollback

`alembic stamp <rev>` rewrites `alembic_version` without touching the
schema. Use it to record that a manual fix equals a revision, or to adopt
an existing database. Using it to "skip" a failing migration leaves the
schema out of sync with the recorded revision.

## Pre-release rollback plan template

```text
Revision: 0006  Lock: SHARE UPDATE EXCLUSIVE (validate), brief ACCESS EXCLUSIVE
Compatible with previous app release? yes (requires v2 writers)
Rollback: app: redeploy v2 | schema: alembic downgrade -1 (drops NOT NULL, no data loss)
Irreversible steps: none | Backup taken: snapshot id ____
Abort conditions: lock_timeout x3, replication lag above agreed limit
```

## Security considerations

- Rollback runs as `migration_owner`, same as upgrade; do not hand the
  app role DDL "to fix it quickly".
- Incident access to the migration credential should be logged and
  time-limited.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `downgrade` fails: `column ... does not exist` | Schema differs from history: compare with `\d` in psql; roll forward instead |
| `Can't locate revision` after rollback of code | Database is ahead of the deployed code; deploy the matching version or roll forward |
| Downgrade blocks production | Cancel it ([above](#a-migration-is-hanging)) and use a lower `lock_timeout` |
| Need old data back | Restore from backup: [07-backups-recovery/point-in-time-recovery.md](../07-backups-recovery/point-in-time-recovery.md), [07-backups-recovery/pg-restore.md](../07-backups-recovery/pg-restore.md) |

## Quick revision

- Revert the app first; schemas that are additive keep the old app working.
- Production default: roll forward. `downgrade` for additive, undepended changes.
- Drops are irreversible without a backup.
- Failed transactional upgrade = full rollback; check for `INVALID` indexes and `autocommit_block()` leftovers.
- Do not edit applied migrations; `stamp` is bookkeeping, not rollback.
