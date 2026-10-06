# Runbook: Disk Full

Applies to PostgreSQL 16. A full data volume stops writes; a full **WAL**
volume can crash the server (`PANIC`). Act fast, but do not delete files
by hand inside the data directory.

## Symptoms

- `ERROR: could not extend file "base/...": No space left on device`
- `PANIC: could not write to file "pg_wal/xlogtemp.NNN": No space left on device` and the server shuts down / restart-loops.
- `ERROR: could not write to file "pg_wal/..."`, `could not create temporary file`.
- Monitoring: data or WAL volume near 100%, WAL directory growing without bound.
- Writes fail while reads still work; on managed services, instance flips to storage-full / read-only.

## Triage (first 2 minutes)

1. **Which volume?** Data, WAL, logs, temp, or backups may be separate mounts (Unix shell):

```bash
df -h                                # per-volume usage; find the 100% one
df -i                                # inode exhaustion looks the same ("No space left")
du -sh "$PGDATA"/* 2>/dev/null | sort -h | tail   # biggest top-level dirs under the data directory
```

Windows (PowerShell): `Get-PSDrive -PSProvider FileSystem` and
`Get-ChildItem 'C:\Program Files\PostgreSQL\16\data' | ForEach-Object { '{0} {1:N0} MB' -f $_.Name, ((Get-ChildItem $_.FullName -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum/1MB) }`.

2. **Which directory dominates?**

| Biggest under `$PGDATA` | Cause | Go to |
|---|---|---|
| `pg_wal/` | WAL not being recycled: stuck replication slot, failing `archive_command`, lagging replica, huge write burst | [A: WAL accumulation](#a-wal-accumulation) |
| `base/` (one database / table) | Genuine growth or bloat | [B: Data growth and bloat](#b-data-growth-and-bloat) |
| `base/pgsql_tmp/` | Runaway query spilling sorts/hashes to temp files | [C: Temp files](#c-temp-files) |
| `log/` (or the log volume) | Verbose logging, no rotation | [D: Logs](#d-logs) |
| Backups on same volume | Local `pg_dump`/base backups filling the disk | Move/prune backups (outside the data directory) |

3. **Stop the growth** (reversible, do now): pause batch jobs, bulk loads, and migrations; stop writers if WAL is exploding.

## Diagnosis

SQL (needs superuser or `pg_monitor`; the file functions need `pg_monitor`
or explicit grants). If the server is already down, see
[database-is-down.md](database-is-down.md) and free space first (below).

### Database and table sizes

```sql
SELECT datname, pg_size_pretty(pg_database_size(datname)) AS size
FROM pg_database ORDER BY pg_database_size(datname) DESC;
```

Run in the large database:

```sql
SELECT schemaname, relname,
       pg_size_pretty(pg_total_relation_size(relid)) AS total,
       pg_size_pretty(pg_relation_size(relid))       AS heap,
       n_live_tup, n_dead_tup, last_autovacuum
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC
LIMIT 10;
```

More: [14-observability/database-size.md](../14-observability/database-size.md).

### A. WAL accumulation

Size of the WAL directory:

```sql
SELECT count(*) AS segments, pg_size_pretty(sum(size)) AS total
FROM pg_ls_waldir();
```

Replication slots holding WAL (the usual cause):

```sql
SELECT slot_name, slot_type, active, wal_status,
       restart_lsn,
       pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS retained_wal,
       safe_wal_size
FROM pg_replication_slots
ORDER BY pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn) DESC NULLS LAST;
```

| Column | Reading |
|---|---|
| `active = f` | No consumer connected: WAL is retained **forever** for it unless `max_slot_wal_keep_size` is set |
| `retained_wal` large | This slot is why `pg_wal/` is big |
| `wal_status` | `reserved` (normal), `extended` (beyond `max_wal_size`, kept by slot), `unreserved` (about to be lost), `lost` (WAL removed; slot unusable) |
| `slot_type` | `physical` (replica) or `logical` (CDC, subscriptions, Debezium) |

Failing WAL archiving (when `archive_mode = on`): PostgreSQL keeps every
segment that has not been archived successfully.

```sql
SELECT archived_count, failed_count, last_archived_wal, last_archived_time,
       last_failed_wal, last_failed_time
FROM pg_stat_archiver;

SELECT count(*) FILTER (WHERE name LIKE '%.ready') AS waiting_for_archive
FROM pg_ls_archive_statusdir();

SHOW archive_mode;
SHOW archive_command;
```

Reproduced with `archive_command = '/bin/false'`: `failed_count` rose,
`last_failed_wal` was set, `waiting_for_archive` grew, and the log
repeated `archive command failed with exit code 1` /
`The failed archive command was: /bin/false`. A rising `failed_count`
with an old `last_archived_time` means archiving is broken.

Connected replicas and lag (primary):

```sql
SELECT application_name, state, sent_lsn, replay_lsn,
       pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn)) AS replay_lag_bytes
FROM pg_stat_replication;
```

Other settings that retain WAL: `wal_keep_size`, `max_wal_size` (soft
target; exceeded under load or when checkpoints cannot complete).

### B. Data growth and bloat

Dead rows are reclaimed by vacuum for *reuse*, but plain `VACUUM` rarely
returns space to the OS ([05-performance/vacuum.md](../05-performance/vacuum.md)).
A growing `n_dead_tup` plus old `last_autovacuum` means vacuum is behind
or **blocked by an old transaction**:

```sql
SELECT pid, usename, application_name, state,
       now() - xact_start AS xact_age, backend_xmin
FROM pg_stat_activity
WHERE backend_xmin IS NOT NULL
ORDER BY age(backend_xmin) DESC
LIMIT 5;
```

Old `xact_age` here, an unused replication slot (`xmin`/`catalog_xmin` in
`pg_replication_slots`), or an abandoned prepared transaction
(`pg_prepared_xacts`) all stop vacuum from removing dead rows.

### C. Temp files

```sql
SELECT datname, temp_files, pg_size_pretty(temp_bytes) AS temp_bytes
FROM pg_stat_database WHERE datname IS NOT NULL ORDER BY temp_bytes DESC;

SELECT * FROM pg_ls_tmpdir();     -- live temp files in the default tablespace
SHOW log_temp_files;
SHOW temp_file_limit;
```

`pg_stat_database.temp_*` are cumulative since stats reset: compare over
time. Find the producing query via [slow-query.md](slow-query.md)
(`temp_blks_written` in `pg_stat_statements`).

### D. Logs

```sql
SHOW log_directory; SHOW logging_collector; SHOW log_min_duration_statement; SHOW log_statement;
```

```bash
du -sh "$PGDATA"/log /var/log/postgresql 2>/dev/null     # Unix shell
```

## Remediation (ordered, safest first)

### 0. Create headroom without touching PostgreSQL files

Do these first; none can damage the database:

| Action | Command (Unix shell) |
|---|---|
| Grow the volume / add disk (cloud: resize volume then `resize2fs`/`xfs_growfs`) | provider console; `sudo xfs_growfs /mountpoint` or `sudo resize2fs /dev/DEVICE` |
| Delete **non-PostgreSQL** files on the same volume: old backups already copied elsewhere, core dumps, unrelated logs | `ls -lh`, then `rm` of files you have verified are copies |
| Rotate/compress **PostgreSQL server logs** (not WAL) | `gzip` old files under `log/`, or `logrotate`; remove only files `pg_current_logfile()` does **not** name |
| Reserved filesystem blocks (ext4) | `sudo tune2fs -m 1 /dev/DEVICE` temporarily frees the root-reserved percentage; record and revert |

### NEVER delete files in `pg_wal/` (destructive, read first)

- **What it does:** removes write-ahead log segments directly from the filesystem.
- **Why risky:** PostgreSQL needs the WAL since the last checkpoint for crash recovery, and replicas/archiving/slots need older segments. Removing the wrong file makes the cluster **unrecoverable** (`could not locate a valid checkpoint record`) or silently breaks replicas and PITR.
- **Safer alternative:** remove the *reason* WAL is retained (drop an abandoned slot, fix archiving, reconnect the replica); PostgreSQL then recycles WAL itself at the next checkpoint. For a manual checkpoint: `CHECKPOINT;` (SQL, superuser).
- **Precaution:** none that makes this safe. The only supported manual tool is `pg_archivecleanup`, for an **archive** directory, never for the live `pg_wal/`.

### A. WAL accumulation fixes

| Cause (from diagnosis) | Action | Risk |
|---|---|---|
| Replica is down but recoverable | Bring the replica back; it consumes the slot and WAL is released | Low |
| `archive_command` failing | Fix the command/credentials/destination; fix the target storage (full bucket, expired token); archiving resumes and old segments are archived then recycled | Low |
| Inactive slot of a consumer that is **gone for good** | Drop the slot (below) | **High**, see caveats |
| Slot is needed but the consumer is slower than WAL generation | Fix consumer throughput; set `max_slot_wal_keep_size` as a safety cap | Medium |
| Write burst after bulk job | Pause it; WAL recycles after checkpoints | Low |

#### `pg_drop_replication_slot` (destructive, read first)

- **What it does:** removes the slot, so PostgreSQL stops retaining WAL for it; space is recycled at the next checkpoints.
- **Why risky:** if the consumer (replica, logical subscriber, CDC tool such as Debezium) is still alive or will return, it can no longer resume. A physical replica must be rebuilt (`pg_basebackup`); a logical consumer needs a re-sync/new snapshot, and changes since its last position are lost to it.
- **Safer alternative:** reconnect or fix the consumer; or set a cap so a slot can never fill the disk: `ALTER SYSTEM SET max_slot_wal_keep_size = '50GB'; SELECT pg_reload_conf();` (value illustrative; a slot that exceeds it becomes `lost` and its consumer must re-sync, which is the deliberate trade of replica health against primary availability).
- **Precaution:** confirm with the owner of the replica/CDC tool that the slot is unused; check `active` is `f` and `active_pid` is null; record `slot_name`, `restart_lsn`, and `slot_type` in the incident notes before dropping.

```sql
SELECT pg_drop_replication_slot('slot_name_from_the_query_above');
```

Reproduced: dropping an inactive physical test slot returned success and
the slot disappeared from `pg_replication_slots`. An **active** slot cannot
be dropped (the call fails with `replication slot "x" is active for PID n`).
Space returns after the next checkpoint(s); run `CHECKPOINT;` to speed it up,
then re-check `pg_ls_waldir()`.

### B. Data growth and bloat fixes

| Action | Notes / risk |
|---|---|
| End the old transaction / drop the unused slot / resolve the prepared transaction that holds back vacuum | Then autovacuum can reclaim; see [lock-contention.md](lock-contention.md) for terminating safely |
| `VACUUM (VERBOSE) table;` | Non-blocking; reuses space but usually **does not shrink the file** |
| Delete data you can lose | See the `DELETE` caveats below |
| Move cold data out, drop old partitions | `DROP`/`DETACH` on a partition is fast and frees space immediately (destructive, below) |
| `VACUUM FULL` | Last resort, below |
| Add disk | Always the safe fix |

#### `DELETE` / `TRUNCATE` at scale (destructive, read first)

- **What it does:** `DELETE` marks rows dead (space is **not** freed until vacuum and usually not returned to the OS) and writes a lot of WAL; `TRUNCATE` removes all rows immediately and frees space.
- **Why risky:** a large `DELETE` on a full disk **makes it worse** first (WAL plus dead tuples) and holds locks; a `DELETE` without `WHERE` or `TRUNCATE` is total, irreversible data loss without a backup.
- **Safer alternative:** delete in small batches with `LIMIT`-style keys and pauses; detach/drop old partitions; copy rows to cold storage first.
- **Precaution:** confirm table and predicate with `SELECT count(*)` using the identical `WHERE`; take or confirm a backup; get lead sign-off; do not run on a disk with no WAL headroom.

#### `VACUUM FULL` (destructive to availability, read first)

- **What it does:** rewrites the table into a new compact file and returns space to the OS.
- **Why risky:** takes an `ACCESS EXCLUSIVE` lock (blocks reads and writes for the whole run) and **needs free space for a full second copy of the table plus its rebuilt indexes**, which is exactly what you do not have when the disk is full. It can fail half-way.
- **Safer alternative:** add disk first; plain `VACUUM`; `pg_repack` (online, needs temporary space too); partition and drop old partitions.
- **Precaution:** maintenance window, free space greater than table plus index size, and run on the single table you identified, not the database.

### C. Temp file fixes

Cancel the runaway query (`pg_cancel_backend(<PID>)`, see [slow-query.md](slow-query.md)); temp files are removed when the query ends. Prevent with
`ALTER ROLE report_user SET temp_file_limit = '20GB';` (value illustrative; queries exceeding it are cancelled with an error). Leftover temp files are
removed by PostgreSQL at restart; do not delete `base/pgsql_tmp/` files by hand while the server runs.

### D. Log fixes

Compress/rotate old logs (Unix shell: `gzip`/`logrotate`), set `log_rotation_age`, `log_rotation_size`, `log_truncate_on_rotation`, and ship logs off the data volume. Reduce `log_statement` / `log_min_duration_statement` if too verbose, then reload (`SELECT pg_reload_conf();`).

### If the server is already down because of a full WAL volume

1. Create space **outside** PostgreSQL's files (grow volume, remove non-PostgreSQL files).
2. Start the server ([database-is-down.md](database-is-down.md)); crash recovery needs some free space to write.
3. Immediately apply fix A (slot/archiving/replica) and `CHECKPOINT;`.

## Verification

```sql
SELECT count(*) AS segments, pg_size_pretty(sum(size)) AS wal_total FROM pg_ls_waldir();
SELECT slot_name, active, wal_status,
       pg_size_pretty(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)) AS retained_wal
FROM pg_replication_slots;
SELECT failed_count, last_archived_time, last_failed_time FROM pg_stat_archiver;
```

```bash
df -h     # Unix shell: volume has headroom and is no longer growing
```

- [ ] Free space is stable or growing, and WAL directory size falls after checkpoints.
- [ ] `failed_count` no longer increases; `waiting_for_archive` returns to near 0.
- [ ] Replicas are streaming and replay lag is falling.
- [ ] Writes succeed; no new `No space left on device` in the log.

## Prevention

- Alert on volume usage at multiple levels (for example warning and critical thresholds; values depend on growth rate and how long a resize takes) **and** on growth *rate*, and on `pg_replication_slots` inactive slots and retained WAL.
- Set `max_slot_wal_keep_size` so an abandoned slot cannot take down the primary; state the tradeoff: the consumer must re-sync if it falls behind that cap.
- Alert on `pg_stat_archiver.failed_count` increases and age of `last_archived_time`.
- Separate volumes for data, WAL, and logs where practical, so one cannot starve the others; keep backups off the data volume.
- Use `temp_file_limit`, `statement_timeout`, and monitor `temp_bytes`.
- Partition time-series tables so retention is a fast partition drop, not a huge `DELETE`.
- Capacity planning and size tracking: [14-observability/database-size.md](../14-observability/database-size.md), [13-cloud-production/scaling.md](../13-cloud-production/scaling.md). Managed services: enable storage autoscaling where offered and verify its limits in the provider documentation ([13-cloud-production/managed-postgresql.md](../13-cloud-production/managed-postgresql.md)).

## Escalation / When to stop

- Server will not start after freeing space and the log shows `could not locate a valid checkpoint record` or missing WAL: stop. Someone may have deleted WAL. Do not run `pg_resetwal`; copy the data directory, then follow [restore-database.md](restore-database.md).
- Slot owner is unknown or is a production CDC/replica you cannot reach: do not drop; escalate to its owner.
- No way to add disk and nothing safe to delete: escalate for emergency capacity; consider promoting a replica or restoring to a larger volume ([restore-database.md](restore-database.md)).
- Filesystem errors or read-only remount in `dmesg`/`journalctl -k`: storage incident, not a PostgreSQL one.

## Not verified here

Reproduced on a throwaway PostgreSQL 16 instance: slot WAL-retention
queries, `pg_ls_waldir()`, `pg_stat_archiver` with a failing
`archive_command`, `pg_ls_archive_statusdir()`, size and temp-file queries,
slot dropping. **Not reproduced:** an actual full-disk condition and the
`PANIC` / startup behavior it causes, volume resizing, logical-slot behavior,
and any cloud provider feature.
