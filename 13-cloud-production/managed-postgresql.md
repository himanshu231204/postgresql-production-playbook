# Managed PostgreSQL

Managed vs self-hosted tradeoffs, what stays your responsibility on a
managed service, maintenance and major-version upgrades, cost levers, and
(in a separate section at the end) provider-specific notes.

## What it is

A managed PostgreSQL service runs the server, OS, storage, backups,
patching, and (optionally) HA for you, and restricts superuser access and
some server-level settings. Self-hosted means you run PostgreSQL on VMs or
containers and own all of that.

## Managed vs self-hosted

Neither wins universally; the table lists what you trade.

| Concern | Managed service | Self-hosted on VMs |
|---|---|---|
| Provisioning, OS and minor patching | Provider | You |
| Backups and PITR | Provider-run, you configure retention and test restores | You build and operate it (see [07-backups-recovery/](../07-backups-recovery/backup-strategy.md)) |
| HA/failover | Toggle, provider-defined topology | You choose and operate it (Patroni-style tooling or equivalent) |
| Superuser / OS access | Restricted | Full |
| Extensions | Provider allowlist | Anything you can install |
| Server parameters | Subset exposed via parameter groups/flags | All |
| Version availability | Provider schedule; old versions reach end of support on the provider's timeline | You decide, within PostgreSQL's own support policy |
| Cost shape | Higher unit price, lower operations labor | Lower unit price, more engineer time and on-call |
| Lock-in surface | Provider-specific networking, IAM auth, proxies, tooling | Mostly portable |
| Observability | Provider metrics, usually limited OS-level visibility | Full host metrics |
| Compliance evidence | Provider attestations help | You produce all evidence |

Pick managed when the team lacks dedicated database operations capacity
or needs the provider's HA/backup integration. Pick self-hosted when you
need an unsupported extension, kernel/storage tuning, or unusual
topologies, and you can staff on-call for it. Check the extension and
parameter you depend on against the provider's current lists before
committing (for example `pgvector`: see
[10-pgvector/installation.md](../10-pgvector/installation.md)).

## What you still own on a managed service

- Schema design, indexes, query performance, vacuum behavior
  ([05-performance/](../05-performance/README.md)).
- Roles, grants, least privilege ([06-security/](../06-security/README.md)).
- Connection management and pooling ([scaling.md](scaling.md)).
- Restore testing: a backup that was never restored is unverified.
- Application behavior on failover ([architecture.md](architecture.md#failover-and-what-the-application-must-handle)).
- Capacity: disk growth, connection count, IOPS/throughput limits.
- Cost.

## Maintenance windows

Managed services apply patches and some parameter changes during a
configurable maintenance window and may restart or fail over the server.

- Set the window to your lowest-traffic period, in the provider's time zone.
- Treat every maintenance event as a mini-failover: the app must reconnect
  (see [architecture.md](architecture.md#failover-and-what-the-application-must-handle)).
- Parameter changes marked "static" or "requires restart" take effect only
  after a restart; schedule them deliberately.
- Alert on provider maintenance notifications instead of discovering them
  from errors.

## Major version upgrades

Minor versions (for example 16.3 to 16.4) are binary swaps and a restart.
Major versions (for example 15 to 16) change the on-disk format and need an
explicit method. Method choice is a tradeoff between downtime, complexity,
and rollback.

| Method | Downtime | Rollback | Caveats |
|---|---|---|---|
| In-place `pg_upgrade` | Server down for the upgrade; `--link` mode is fast but shares files with the old cluster | Easy only before the new cluster is started in link mode; afterwards restore from backup | Planner statistics are not carried over: run `ANALYZE` (e.g. `vacuumdb --all --analyze-in-stages`) before reopening traffic. Check extension compatibility first |
| Logical replication to a new cluster | Seconds to minutes at cutover | Keep the old primary; reverse replication is manual | DDL and sequence values are not replicated: copy sequences at cutover and freeze schema changes. Tables need a primary key or replica identity. Large objects are not replicated |
| Provider blue/green or "managed major upgrade" | Provider-defined (see provider notes) | Provider-defined | Still test the application against the new version first |
| Dump and restore (`pg_dump`/`pg_restore`) | Proportional to data size | Old instance untouched | Only for small databases or when a long window is acceptable |

Upgrade procedure, any method:

1. Read the release notes for every major version crossed
   (https://www.postgresql.org/docs/release/) for incompatibilities.
2. Restore a recent backup into a staging environment and upgrade it with
   the chosen method; run the application's test suite and the slowest
   production queries.
3. Compare plans for critical queries (`EXPLAIN`) before and after; see
   [05-performance/explain.md](../05-performance/explain.md).
4. Take a fresh backup and confirm it restores.
5. Schedule inside a maintenance window with a rollback decision point.
6. After cutover: `ANALYZE`, check errors and latency, keep the old
   instance until the rollback window closes.

Related: migrations during upgrade windows are riskier; avoid combining a
schema migration with a major upgrade
([09-alembic/production-migrations.md](../09-alembic/production-migrations.md)).

## Cost levers

No prices here; they change. Levers, with the tradeoff:

| Lever | Saves by | Tradeoff |
|---|---|---|
| Right-size instance from measured CPU, memory, connection and IOPS use | Paying for headroom you do not use | Less headroom for spikes; resize needs a restart on most services |
| Pooler instead of a larger instance | Smaller instance sustains the same client count | Pooler is one more component |
| Drop unused indexes (verify with `pg_stat_user_indexes`) | Storage and write amplification | Check the full business cycle (month-end jobs) before dropping |
| Retention of backups and logs | Storage | Shorter recovery window; compliance minimums |
| Read replicas only where reads justify them | Each replica is a full instance | More replicas means more lag and routing code |
| HA only for production | Standby costs roughly a second instance | Staging and dev lose failover fidelity |
| Reserved/committed pricing (if the provider offers it) | Lower rate for steady load | Commitment risk if you migrate or downsize |
| Storage bloat control (vacuum, partition and drop old data) | Storage and IO | Operational work; see [05-performance/vacuum.md](../05-performance/vacuum.md) |
| Same-region traffic between app and database | Cross-zone/region data transfer fees, where billed | Zone placement conflicts with HA spread; check the provider's billing rules |
| Stop or scale down non-production when idle | Compute | Startup delay; confirm the provider's rules for stopped instances |

## Common mistakes

- Choosing managed and assuming backups, restores, and failover were
  tested for you.
- Relying on a provider-specific feature (IAM auth, proxy endpoint) with
  no portability or exit plan, without writing the decision down.
- Running a major upgrade first in production.
- Letting the maintenance window default to business hours.
- Sizing from "it worked in staging" with a fraction of connections.

## Security considerations

Shared-responsibility: the provider secures the platform; you secure
roles, networking rules, TLS settings, and secrets. See
[networking.md](networking.md), [ssl-tls.md](ssl-tls.md),
[secrets.md](secrets.md), and
[06-security/security-checklist.md](../06-security/security-checklist.md).

## Quick revision

- Managed removes undifferentiated operations, not responsibility for
  schema, queries, roles, restore testing, and failover behavior.
- Major upgrades: choose pg_upgrade, logical replication, or provider
  blue/green by downtime vs rollback needs; rehearse on a restored copy;
  `ANALYZE` afterward.
- Cost levers: right-size, pool, prune indexes, bound retention, replicas
  only when justified.

---

## Provider notes

Provider-specific. Everything above this heading is vendor-neutral. The
notes below are limited to statements checked against each provider's
official documentation; features that could not be verified were left
out. Provider behavior, limits, and defaults change: re-check the linked
page before relying on a point. Nothing here was executed against a live
account (none was available).

Verified against docs on 2026-10-06. Aurora (AWS), AlloyDB (Google Cloud),
and other products were not checked and are not covered.

### AWS: Amazon RDS for PostgreSQL

1. **Multi-AZ has two shapes.** A Multi-AZ DB instance deployment has one
   standby that provides failover support but does not serve read
   traffic. A Multi-AZ DB cluster deployment has two standbys that provide
   failover and can also serve read traffic.
   Docs: <https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Concepts.MultiAZ.html>
2. **TLS enforcement is a parameter.** `rds.force_ssl` defaults to `1` for
   RDS for PostgreSQL 15 and later and `0` for 14 and older. Changing it
   needs a custom DB parameter group; on a running instance you must
   reboot so it uses the custom group. libpq clients default to `prefer`,
   so set `sslmode` on the client regardless.
   Docs: <https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/PostgreSQL.Concepts.General.SSL.html>
3. **CA bundles.** AWS publishes a global bundle and per-region bundles;
   register only root CA certificates in the trust store, not
   intermediates. Default CA for new instances is `rds-ca-rsa2048-g1`.
   RDS manages and rotates the server certificate.
   Docs: <https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.SSL.html>
4. **RDS Proxy** pools connections and connects to a standby on failure.
   Documented limits for PostgreSQL include: the proxy must be in the same
   VPC as the database and cannot be publicly accessible; for instances in
   a replication configuration you can associate a proxy only with the
   writer, not a read replica; it does not support `CancelRequest`
   (Ctrl+C cancel in `psql` through the proxy); the `lastval()` result is
   not always accurate (use `INSERT ... RETURNING`). Clients of the proxy
   use AWS Certificate Manager certificates, not the RDS CA bundle.
   Docs: <https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy.html>
5. **Blue/Green Deployments** support RDS for PostgreSQL, create a synced
   staging copy where you can change the engine major version, and switch
   over typically in under a minute with no data loss (docs: "can be longer
   depending on your workload"). For RDS for PostgreSQL, logical
   replication is used in certain conditions instead of physical.
   Docs: <https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/blue-green-deployments-overview.html>
6. **Read replicas** use PostgreSQL's native replication and are
   read-only; point-in-time recovery is not supported on a read replica
   (only on the writer). Promoting a replica is irreversible. A replica
   with no source activity can report lag up to five minutes until a WAL
   segment switch, so lag alerts must account for idle periods.
   Docs: <https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_PostgreSQL.Replication.ReadReplicas.html>

### Azure: Azure Database for PostgreSQL flexible server

1. **Networking is chosen at creation:** private access (virtual network
   integration, server injected into a delegated subnet, a Private DNS
   zone required) or public access with allowed IPs plus private
   endpoint. A server cannot be moved to another virtual network or
   subnet after deployment, and the subnet cannot be enlarged once
   resources exist. Use the server FQDN, not an IP address.
   Docs: <https://learn.microsoft.com/en-us/azure/postgresql/network/concepts-networking-private>
2. **NSG rules:** high availability needs traffic to destination port
   5432 within the server's subnet and to Azure Storage (service tag
   `Storage`); NSG rules using an application security group are not
   supported (use IP-based filtering). Resource locks on the Private DNS
   zone or records can interfere with HA failover DNS updates.
   Same page as note 1.
3. **High availability** replicates synchronously to a standby in another
   zone (zone-redundant) or the same zone (zonal). The standby cannot
   serve reads. Clients connect to the primary's hostname; on failover
   the DNS entry is updated. Docs state zone-redundant failover completes
   "within 60-120 seconds" with zero data loss, and can take longer
   depending on recovery. HA does not protect against logical errors:
   they replicate, so use point-in-time restore.
   Docs: <https://learn.microsoft.com/en-us/azure/postgresql/high-availability/concepts-high-availability>
4. **Built-in PgBouncer** runs on the database VM, on port 6432 (same
   hostname), default pool mode `transaction`; enable with
   `pgbouncer.enabled`. Not supported on the Burstable compute tier. It
   restarts on the new primary after failover, so the connection string
   does not change.
   Docs: <https://learn.microsoft.com/en-us/azure/postgresql/connectivity/concepts-pgbouncer>
5. **TLS:** the service requires TLS (1.2 and 1.3); `require_secure_transport`
   controls enforcement. Docs recommend trusting the root CAs
   (DigiCert Global Root G2 and Microsoft RSA Root CA 2017 currently),
   never intermediate CAs or individual server certificates, and never
   certificate pinning, because intermediates and server certificates
   rotate without announcement. The page recommends full certificate
   and hostname verification and notes that, depending on DNS setup with
   private endpoints or virtual network integration, only CA verification
   (`verify-ca`) may be possible. It writes the full mode as `verify-all`;
   libpq's name is `verify-full`. Client-certificate (mutual TLS)
   authentication and custom server certificates are not supported.
   Docs: <https://learn.microsoft.com/en-us/azure/postgresql/security/security-tls>
6. **Maintenance window:** you can schedule Azure-initiated maintenance
   into a 60-minute window; otherwise the system picks a one-hour window
   between 11 PM and 7 AM local time. Customer-initiated management tasks
   cannot be scheduled during the managed window. Same page as note 3.

### Google Cloud: Cloud SQL for PostgreSQL

1. **HA** creates a regional instance with a primary and a secondary
   zone; writes are synchronously replicated to persistent disks in both
   zones before commit is reported. On failure the standby becomes the
   primary and the application reconnects with the same connection
   string or IP. Docs recommend automated backups alongside HA. The
   standby is a failover target; the page does not describe it serving
   reads.
   Docs: <https://docs.cloud.google.com/sql/docs/postgres/high-availability>
2. **`ssl_mode`** values: `ALLOW_UNENCRYPTED_AND_ENCRYPTED` (the default),
   `ENCRYPTED_ONLY`, `TRUSTED_CLIENT_CERTIFICATE_REQUIRED`. Set
   `ENCRYPTED_ONLY` or stricter. Server certificates are created for the
   instance; with a shared CA or custom DNS the docs recommend hostname
   verification (`sslmode=verify-full` in `psql`, checked against the
   certificate SAN).
   Docs: <https://docs.cloud.google.com/sql/docs/postgres/configure-ssl-instance>
3. **Cloud SQL Auth Proxy** connections are automatically encrypted and
   the client and server identities are verified regardless of the SSL
   mode setting. Same page as note 2.
4. **Private IP** uses private services access (built on VPC Network
   Peering, which is not transitive) or Private Service Connect. An
   instance can use private IP only; once private IP is configured it
   cannot be removed from the instance.
   Docs: <https://docs.cloud.google.com/sql/docs/postgres/private-ip>
5. **Managed connection pooling** offers transaction mode (default) and
   session mode, listens on port 6432 (direct) and 3307 (Auth Proxy
   path), and requires Enterprise Plus edition and a minimum maintenance
   version. Enabling it on an existing instance triggers a restart.
   Transaction-mode limits include no `SET`/`RESET`, `LISTEN`,
   `PREPARE`/`DEALLOCATE`, temp tables, or session-level advisory locks.
   Docs: <https://docs.cloud.google.com/sql/docs/postgres/managed-connection-pooling>
