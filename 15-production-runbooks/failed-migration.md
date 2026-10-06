# Runbook: Failed Migration

Applies to PostgreSQL 16 and Alembic (SQLAlchemy 2.x projects); the
PostgreSQL parts apply to any migration tool. The first question is always:
**what state did the failure leave the database in?**

## Symptoms

- Deploy pipeline step "run migrations" failed, hung, or was cancelled.
- Migration process is running for far longer than expected; other queries stall (see [lock-contention.md](lock-contention.md)).
- App errors after deploy: `column "x" does not exist`, `relation "x" does not exist`, `null value in column ... violates not-null constraint`, constraint violations.
- `alembic upgrade head` fails; re-running fails differently (`relation already exists`, `duplicate column`).
- An index shows `INVALID` in `\d table`.

## Triage (first 2 minutes)

1. **Stop further migration attempts** and pause the deploy. Do not re-run blindly.
2. Is the migration still running? (SQL)

```sql
SELECT pid, application_name, state, wait_event_type, wait_event,
       now() - xact_start  AS xact_age,
       now() - query_start AS query_age,
       left(query, 100)    AS query
FROM pg_stat_activity
WHERE backend_type = 'client backend'
  AND (query ILIKE 'alter table%' OR query ILIKE 'create index%' OR query ILIKE 'drop %'
       OR application_name ILIKE '%migrat%' OR application_name ILIKE '%alembic%')
  AND pid <> pg_backend_pid();
```

3. Classify with this table:

| What failed | State left behind | Go to |
|---|---|---|
| Ordinary DDL/DML migration in **one transaction** (PostgreSQL has transactional DDL) | Everything rolled back: schema unchanged, `alembic_version` unchanged | [Case A](#case-a-transactional-migration-rolled-back) |
| Migration split into several transactions or run as separate statements without `--single-transaction` | **Partial**: some statements committed, later ones did not | [Case B](#case-b-partial-application) |
| `CREATE INDEX CONCURRENTLY` failed or was cancelled | Index exists but is `INVALID` | [Case C](#case-c-invalid-indexes-after-create-index-concurrently) |
| Migration is **blocked/waiting** (lock queue) | Nothing applied yet; but it is stalling live traffic | [Case D](#case-d-migration-stuck-on-a-lock) |
| Migration succeeded but the **app** is broken (old code vs new schema) | Schema is new, code is incompatible | [Case E](#case-e-schema-applied-but-the-app-is-failing) |

## Diagnosis

### What does the migration tool think? (Unix shell)

```bash
alembic current            # revision recorded in alembic_version
alembic heads              # latest revision in the code
alembic history --verbose | head -30
```

(`alembic ... -x` / env variables set `DATABASE_URL` as your project
configures it; use the **migration role**, not the app role.)

What does the database say? (SQL)

```sql
SELECT * FROM alembic_version;      -- one row: the current revision
```

`alembic_version` is updated **inside the same transaction** as the
migration when the migration runs transactionally, so a rolled-back
migration leaves it at the old revision. If the version table and the real
schema disagree, you are in Case B.

### What does the schema actually contain? (psql meta-commands)

```text
\d+ orders          -- columns, indexes (INVALID is marked), constraints, triggers
\di+ public.*       -- indexes and sizes
```

(`\d+` and `\di+` are psql client commands, not SQL.)

### Invalid indexes (SQL)

```sql
SELECT n.nspname AS schema, t.relname AS table_name, c.relname AS index_name,
       i.indisvalid, i.indisready,
       pg_size_pretty(pg_relation_size(i.indexrelid)) AS size
FROM pg_index i
JOIN pg_class c     ON c.oid = i.indexrelid
JOIN pg_class t     ON t.oid = i.indrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE NOT i.indisvalid;
```

### Other things a failed migration leaves (SQL)

```sql
SELECT conrelid::regclass AS table_name, conname, convalidated      -- NOT VALID constraints never validated
FROM pg_constraint WHERE NOT convalidated;

SELECT gid, prepared, owner, now() - prepared AS age FROM pg_prepared_xacts;   -- abandoned prepared txns
```

## Remediation (ordered, safest first)

### Case A: transactional migration rolled back

PostgreSQL DDL is transactional: if the migration ran in one transaction
and failed, **nothing was applied**. Reproduced: `BEGIN; ALTER TABLE ... ADD
COLUMN note; CREATE INDEX ON ... (nonexistent); COMMIT;` raised
`column "nonexistent" does not exist` and the added column was not present
afterwards.

1. Confirm: `alembic current` equals the previous revision, and `\d+ table` shows the old schema.
2. Read the error, fix the migration **in a new commit**, run it again.
3. Do not edit a migration that has already been applied in any real environment. Fix forward with a new revision. Hand-editing applied history causes drift between migration history and schema ([09-alembic/rollback-strategies.md](../09-alembic/rollback-strategies.md)).

### Case B: partial application

Happens when migrations are not wrapped in one transaction: Alembic with
`transaction_per_migration`, `autocommit_block()`, `op.execute` of
multi-statement scripts run in autocommit, hand-run `psql -f` scripts, or
non-transactional statements in the file. Reproduced: running a two-statement
script with `psql -f` (autocommit, `ON_ERROR_STOP=1`) applied the first
statement, failed on the second, and **left the first applied**; the same
script with `psql --single-transaction` left nothing.

1. Compare the migration's intended steps with the actual schema (`\d+`, queries above). Write down which steps applied.
2. Choose, in this order:
   - **Complete forward:** write a new revision (or manual, reviewed SQL) that applies the missing steps idempotently (`ADD COLUMN IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`) and let the tool record it.
   - **Reverse the applied part:** run the matching `downgrade` steps by hand for only what applied. Destructive reversals (dropping a column that now contains data) need a backup first.
3. Reconcile the tool's state with reality **only after** the schema matches the target revision. `alembic stamp <revision>` sets the version row without running any SQL.

#### `alembic stamp` (risky, read first)

- **What it does:** writes the revision into `alembic_version` without executing migrations.
- **Why risky:** if the schema does not actually match that revision, every later migration runs against a schema the tool believes is something else. Drift is silent until it fails in production.
- **Safer alternative:** run `alembic upgrade`/`downgrade` so the tool executes the SQL itself, in a transaction.
- **Precaution:** verify schema equals the target revision column-by-column first (`alembic check` / autogenerate diff on a copy, and `\d+`); record the stamp in the incident timeline.

### Case C: invalid indexes after `CREATE INDEX CONCURRENTLY`

`CREATE INDEX CONCURRENTLY` cannot run inside a transaction block
(`ERROR: CREATE INDEX CONCURRENTLY cannot run inside a transaction block`;
in Alembic use `with op.get_context().autocommit_block():`). If it fails or
is cancelled mid-way it leaves the index behind marked `INVALID`.
Reproduced: building a `UNIQUE` index on a column with duplicates failed with

```text
ERROR:  could not create unique index "ix_events_user_ref"
DETAIL:  Key (user_ref)=(u26) is duplicated.
```

and `\d events` then showed `"ix_events_user_ref" UNIQUE, btree (user_ref) INVALID`;
the query above returned it with `indisvalid = f`. Common causes: duplicate
keys for a unique index, cancelled/timed-out build (`statement_timeout`,
`pg_cancel_backend`), deadlock, server restart mid-build.

An invalid index is **not used by queries** but is still **maintained on every
write** (cost without benefit; for unique indexes it may still enforce
uniqueness on writes). Remove it and retry:

| Step | Command (SQL) | Notes |
|---|---|---|
| 1. Fix the cause | e.g. find duplicates: `SELECT user_ref, count(*) FROM events GROUP BY user_ref HAVING count(*) > 1;` | Resolve data issues first |
| 2. Drop the invalid index | `DROP INDEX CONCURRENTLY IF EXISTS ix_events_user_ref;` | See risk note below |
| 3. Rebuild | `CREATE INDEX CONCURRENTLY ix_events_user_ref ON events (user_ref);` | Outside a transaction block |
| 4. Verify | `indisvalid` query above returns no row for it; `EXPLAIN` uses it | |

Alternative to 2 and 3: `REINDEX INDEX CONCURRENTLY ix_events_user_ref;`
(PostgreSQL 12+) rebuilds an invalid index in place; if it fails it also
leaves a leftover invalid `..._ccnew` index to drop.

#### `DROP INDEX` (destructive, read first)

- **What it does:** deletes the index and its storage.
- **Why risky:** plain `DROP INDEX` takes `ACCESS EXCLUSIVE` on the table (blocks reads and writes); dropping the **wrong** (valid, in-use) index causes sudden query slowdowns.
- **Safer alternative:** `DROP INDEX CONCURRENTLY` (does not block normal operations; cannot run in a transaction block, cannot drop an index backing a constraint).
- **Precaution:** drop only indexes where `indisvalid = false`, copy the name from the query result; for a replaced valid index, build the new one first, verify with `EXPLAIN`, then drop the old.

### Case D: migration stuck on a lock

A migration waiting for `ACCESS EXCLUSIVE` queues **all** later queries on
that table behind itself (reproduced; details in
[lock-contention.md](lock-contention.md#the-ddl-lock-queue)). Fastest relief,
safest first:

1. **Cancel the migration's statement:** `SELECT pg_cancel_backend(<PID>);` from the triage query. Waiting readers/writers proceed immediately (reproduced). The migration rolled back (Case A). Nothing destructive happened.
2. Resolve the blocker (an old `idle in transaction` session), per [lock-contention.md](lock-contention.md).
3. Re-run the migration with a guard so it fails fast instead of queuing traffic, and retry in a quiet period:

```sql
SET lock_timeout = '5s';          -- inside the migration session, before the DDL
ALTER TABLE orders ADD COLUMN note text;
```

Reproduced: a session with `lock_timeout = '1s'` failed with
`ERROR: canceling statement due to lock timeout` instead of waiting.

### Case E: schema applied but the app is failing

First decide by compatibility, not by reflex. A deploy order mismatch is the
usual cause:

| Situation | Action |
|---|---|
| New code deployed before the migration ran (or migration failed) | Roll the **code** back to the previous version (it matches the old schema), or complete the migration |
| Migration added a column the old code does not know | Usually harmless: old code ignores it. Roll back code only if needed |
| Migration **dropped/renamed** a column the old code still uses | Do not "roll back" blindly: the data may be gone. Restore the old name/column compatibly (new migration), or ship the code fix. See [09-alembic/production-migrations.md](../09-alembic/production-migrations.md) |
| Migration added `NOT NULL` / constraint the old code violates | Relax it in a new forward migration (`ALTER COLUMN ... DROP NOT NULL`, drop the constraint) while code is fixed |

#### Downgrade in production (destructive, read first)

- **What it does:** `alembic downgrade <revision>` runs each migration's `downgrade()` (often dropping columns, tables, indexes).
- **Why risky:** drops data written since the upgrade; many downgrades are lossy or untested; it takes locks of the same kind as the upgrade.
- **Safer alternative:** a **forward** fix migration; roll back application code instead; restore the dropped column from backup ([restore-database.md](restore-database.md)).
- **Precaution:** read the downgrade SQL first (`alembic downgrade <from>:<to> --sql` prints it without running), back up the affected tables (`pg_dump -t table`), run in a window, and confirm the old code is what you want to serve. More: [09-alembic/rollback-strategies.md](../09-alembic/rollback-strategies.md).

## Verification

```bash
alembic current        # (Unix shell) expected revision; no "(head)" mismatch with intent
alembic check          # no pending autogenerate differences (if you use it)
```

```sql
SELECT * FROM alembic_version;
SELECT count(*) AS invalid_indexes FROM pg_index WHERE NOT indisvalid;      -- expect 0
SELECT count(*) AS not_valid_constraints FROM pg_constraint WHERE NOT convalidated;  -- expect 0 (or known, planned VALIDATE)
SELECT count(*) AS waiting FROM pg_stat_activity WHERE cardinality(pg_blocking_pids(pid)) > 0;  -- expect 0
```

- [ ] `alembic_version` equals the schema's real state (verified with `\d+`, not assumed).
- [ ] App health checks and a smoke test against the changed tables pass.
- [ ] No sessions waiting on locks; migration processes finished.
- [ ] Postmortem items filed (what rehearsal would have caught this).

## Prevention

| Practice | Why |
|---|---|
| Run every migration against a **production-sized copy** first; time it and check lock levels | Surfaces slow rewrites and long locks before production |
| `SET lock_timeout` (and sensible `statement_timeout`) at the top of each migration; retry on timeout | A migration that cannot get its lock should fail fast |
| `CREATE INDEX CONCURRENTLY` in an `autocommit_block`; verify `indisvalid` after | Avoids blocking writes; catches the INVALID leftover |
| Add constraints `NOT VALID`, then `VALIDATE CONSTRAINT` separately | Short lock, then a non-blocking validation |
| Expand/contract: add nullable column, deploy code, backfill in batches, then add constraints; drop columns only in a later release | Old and new code both run against the mid-migration schema |
| Deployment order: migrate first for additive changes, deploy code first for removals | Keeps every version compatible with the live schema |
| Separate roles: migration role (DDL) vs app role (CRUD) | Least privilege; see [06-security/least-privilege.md](../06-security/least-privilege.md) |
| Back up (or snapshot) before destructive migrations; know the PITR path | Rollback of data needs a restore, not `downgrade` |
| Never edit a migration that has already been applied in a real environment | Prevents history/schema drift |

Details: [09-alembic/production-migrations.md](../09-alembic/production-migrations.md),
[09-alembic/rollback-strategies.md](../09-alembic/rollback-strategies.md).

## Escalation / When to stop

- Schema and `alembic_version` disagree and you cannot say which statements applied: stop running migrations; snapshot the database; have a second engineer review before any `stamp` or manual SQL.
- Migration touched a very large table (rewrite, `VALIDATE`, backfill) and is still running: do not terminate repeatedly; a cancelled rewrite is rolled back (can take time) and restarting repeats the work. Escalate for a batching plan.
- Data loss from a dropped/changed column or `UPDATE` without `WHERE`: stop writes to the table and go to [restore-database.md](restore-database.md) (restore to a new instance, extract the data, repair forward).
- The migration affects a replica set or logical replication (DDL is not replicated logically): escalate before proceeding.
