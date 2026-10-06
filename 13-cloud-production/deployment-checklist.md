# Cloud Deployment Checklist

Go-live audit for PostgreSQL in the cloud. Each item links to the page
that explains it. Complements
[06-security/security-checklist.md](../06-security/security-checklist.md)
and [05-performance/performance-checklist.md](../05-performance/performance-checklist.md).
Tick an item only after verifying it in the target environment.

## Network

- [ ] Database has no public IP; DB subnet has no internet route —
      [networking.md](networking.md).
- [ ] Inbound 5432 (or pooler port) allowed only from the app/pooler
      security group or narrowest CIDR; no `0.0.0.0/0`.
- [ ] Admin access via bastion/VPN with individual identity.
- [ ] Database hostname resolves privately from the app, migration job,
      and CI networks.
- [ ] Connection strings use the hostname, never an IP.

## TLS and authentication

- [ ] Server requires TLS (provider flag/parameter) — verified with a
      `sslmode=disable` attempt that fails —
      [ssl-tls.md](ssl-tls.md).
- [ ] All clients (app, pooler, migrations, BI tools) use
      `sslmode=verify-full` with the provider CA bundle; or a documented,
      compensated exception.
- [ ] CA bundle shipped in image/config; process exists to update it
      before provider rotations; no intermediate or server certificates
      pinned.
- [ ] `SELECT ... FROM pg_stat_ssl` shows `ssl = t` for every client
      backend.

## Secrets and roles

- [ ] Credentials in a secrets manager; app reads via workload identity —
      [secrets.md](secrets.md).
- [ ] Separate application, migration, and admin roles; app has no DDL —
      [06-security/least-privilege.md](../06-security/least-privilege.md).
- [ ] Rotation rehearsed end to end, including the pooler.
- [ ] No secrets in repo, images, CI logs, or compose files.

## Availability and recovery

- [ ] HA configured as intended (zones, synchronous behavior understood)
      — [architecture.md](architecture.md).
- [ ] Failover tested under load; downtime measured from the application;
      reconnect, backoff with jitter, and idempotent retries confirmed.
- [ ] Automated backups on; retention matches the recovery objective —
      [07-backups-recovery/backup-strategy.md](../07-backups-recovery/backup-strategy.md).
- [ ] PITR enabled and a restore into a new instance completed, with
      timing recorded —
      [07-backups-recovery/point-in-time-recovery.md](../07-backups-recovery/point-in-time-recovery.md).
- [ ] Disaster-recovery scope decided (cross-region copy or replica or
      accepted risk) —
      [07-backups-recovery/disaster-recovery.md](../07-backups-recovery/disaster-recovery.md).
- [ ] Deletion protection / delete locks enabled on the instance where the
      provider offers them (verify in provider docs).

## Capacity and connections

- [ ] Connection budget computed at maximum autoscaling — [scaling.md](scaling.md).
- [ ] Pooler deployed and pool mode matches app behavior (prepared
      statements, advisory locks, `SET`).
- [ ] Per-role `CONNECTION LIMIT`, `statement_timeout`, and
      `idle_in_transaction_session_timeout` set.
- [ ] Instance size, storage, and IOPS/throughput chosen from load tests;
      storage autoscaling or alerts at a stated threshold.
- [ ] Read replicas (if any): routing rules and read-after-write handling
      documented.

## Operations

- [ ] Maintenance window set to low-traffic period; app tolerates the
      restart/failover it can cause —
      [managed-postgresql.md](managed-postgresql.md#maintenance-windows).
- [ ] Major-version upgrade plan chosen and rehearsed on a restored copy.
- [ ] Monitoring and alerts: connections, replication lag, disk/WAL
      growth, CPU/memory/IO, failover events, certificate expiry —
      [14-observability/monitoring.md](../14-observability/monitoring.md),
      [14-observability/health-checks.md](../14-observability/health-checks.md).
- [ ] Logs retained and access-controlled; slow-query logging or
      `pg_stat_statements` available.
- [ ] Runbooks linked from the on-call page —
      [15-production-runbooks/](../15-production-runbooks/README.md).
- [ ] Migrations follow the production-safety rules —
      [09-alembic/production-migrations.md](../09-alembic/production-migrations.md).

## Cost

- [ ] Environments right-sized; non-production does not run production HA
      by default.
- [ ] Backup, log, and snapshot retention reviewed.
- [ ] Budget alert set on the database spend.

## Quick revision

- Private, TLS-verified, secrets-managed, pooled.
- HA tested, backups restored, failover timed.
- Alerts and runbooks exist before the first incident.
