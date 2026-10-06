# Backup Strategy

## What it is

The decision of what to back up, how (logical vs. physical), how often,
where copies live, how long they are kept, and how restores are proven.

## Why it matters

Strategy is derived from two numbers the business must accept:

| Term | Meaning | Drives |
|---|---|---|
| **RPO** (Recovery Point Objective) | Maximum tolerable data loss, measured in time | Backup frequency; whether WAL archiving is needed |
| **RTO** (Recovery Time Objective) | Maximum tolerable time to be back in service | Backup size, restore method, standby use, practice |

A nightly `pg_dump` gives an RPO of up to ~24 hours. An RPO of minutes
requires continuous WAL archiving or a streaming replica. RTO is bounded
by restore speed: measure it by restoring, not by estimating.

## Logical vs. physical

| | Logical (`pg_dump`, `pg_dumpall`) | Physical (`pg_basebackup` + WAL archive) |
|---|---|---|
| Unit | One database (or schema/table) as SQL/archive | Entire cluster data directory |
| Restore to | Same or newer major version, any architecture | Same major version and architecture only |
| Point-in-time recovery | No | Yes, with archived WAL |
| Selective restore (one table) | Yes | No (restore whole cluster, then extract) |
| Speed on large data | Slower to dump and restore (rebuilds indexes) | Faster (file copy; indexes are copied) |
| Consistency | Consistent snapshot of the one database | Consistent cluster, replayed from WAL |
| Includes roles/tablespaces | No: use `pg_dumpall --globals-only` | Yes |
| Use for | Migration, upgrade, small/medium DBs, per-DB restore | Production DR, PITR, large DBs |

Tradeoff, not a ranking: most production systems run both. Physical
backups plus WAL for disaster recovery and PITR; periodic logical dumps
for portability, major-version upgrades, and single-table recovery.
Dumps run in a single transaction snapshot and hold it for the whole
run; on a busy primary a long dump delays vacuum cleanup (see
[05-performance/vacuum.md](../05-performance/vacuum.md)).

## The 3-2-1 rule

- **3** copies of the data (production plus two backups)
- **2** different storage media or systems
- **1** copy off-site (different region/account); keep one copy that the
  production credentials cannot delete (object-lock / immutable bucket,
  or a separate account), so ransomware or a compromised host cannot
  erase every backup

## Retention

Set retention from requirements (compliance, how long a silent
corruption could go unnoticed), not a default. A common shape, shown as
an illustration: daily backups for 7 days, weekly for 4 weeks, monthly
for 12 months. Keep WAL archive from the oldest retained base backup
forward; a base backup without its WAL range is not point-in-time
recoverable.

## Encryption

- **In transit**: connect with `sslmode=verify-full` (see
  [06-security/ssl.md](../06-security/ssl.md)); use TLS to object storage.
- **At rest**: `pg_dump` and `pg_basebackup` do not encrypt output.
  Encrypt before upload: storage-level encryption (encrypted volume,
  bucket SSE with a customer-managed key), or file-level (`gpg`,
  `age`). pgBackRest and Barman provide their own encryption options
  (check their docs for the exact settings).
- Dumps contain all data and, via `pg_dumpall`, role password hashes.
  Treat them as production data: restrict file mode (`umask 077`),
  restrict bucket access, never place them in a repository.
- Store keys separately from backups. A backup whose key was lost with
  the server is unrecoverable.

## Tools

| Tool | What it is | Tradeoff |
|---|---|---|
| `pg_dump` / `pg_restore` | Built in; logical | Simple and portable; no PITR; slow at large size |
| `pg_basebackup` + `archive_command` | Built in; physical | No dependencies; you build scheduling, retention, and verification yourself |
| pgBackRest | External physical backup manager: full/differential/incremental, parallel, retention, verification, cloud storage | Another component to deploy, configure, and monitor; much less custom scripting |
| Barman | External physical backup/DR manager run from a separate backup server | Same: centralized management at the cost of another system |
| Managed-service snapshots / PITR | Provider feature | Convenient; limited to provider's retention, regions, and restore mechanics (see [13-cloud-production/managed-postgresql.md](../13-cloud-production/managed-postgresql.md)) |

Read the tool's official documentation for configuration; this
repository does not reproduce tool-specific flags.

## Restore testing

An untested backup has an unknown RPO and RTO. On a schedule:

1. Restore the latest backup to an isolated scratch instance (never the
   production host).
2. Run sanity queries (row counts on key tables, newest timestamp,
   application smoke test).
3. Record elapsed restore time; compare to RTO.
4. For PITR, also recover to a recent timestamp and confirm it.
5. Alert if a backup job fails or the newest backup is older than the RPO.

Automate with [scripts/restore/restore.sh](../scripts/restore/restore.sh).

## Common mistakes

- Backups stored on the same disk, host, or account as the database.
- Never testing a restore; discovering at incident time that the dump is
  empty, truncated, or needs a missing role.
- Backing up the database but not the roles (`pg_dumpall --globals-only`),
  config files (`postgresql.conf`, `pg_hba.conf`), or application secrets.
- Copying a live data directory with `cp`/`rsync` without
  `pg_basebackup` or the low-level backup API: the copy is inconsistent.
- Archiving WAL with a command that silently fails; `pg_wal` then fills
  the disk (see [15-production-runbooks/disk-full.md](../15-production-runbooks/disk-full.md)).
- Running `pg_dump` and `pg_restore` from a client older than the server.
  Use a client of the same or newer major version as the server.

## Quick revision

- Define RPO/RTO first; pick the mechanism second.
- Dump for portability, base backup + WAL for DR and PITR; often both.
- 3-2-1, with one immutable off-site copy.
- Encrypt output yourself; backups hold everything.
- Restore on a schedule and time it.

See also: [pg-dump.md](pg-dump.md), [point-in-time-recovery.md](point-in-time-recovery.md),
[disaster-recovery.md](disaster-recovery.md).
