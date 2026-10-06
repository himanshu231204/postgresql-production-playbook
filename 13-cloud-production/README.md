# Cloud Production Overview

Vendor-neutral guidance for running PostgreSQL in production on a managed
service or on cloud VMs: topology, private networking, TLS, secrets, HA,
scaling, and a pre-launch checklist. Provider-specific details (AWS,
Azure, Google Cloud) are isolated in clearly labeled "Provider notes"
sections in [managed-postgresql.md](managed-postgresql.md#provider-notes).

## Pages

| Page | Use it for |
|---|---|
| [architecture.md](architecture.md) | Reference topology (Mermaid), HA vs read replicas vs backups, sync vs async replication, failover and what the app must handle |
| [managed-postgresql.md](managed-postgresql.md) | Managed vs self-hosted tradeoffs, what you still own, cost levers, maintenance and major upgrades, **provider notes** |
| [networking.md](networking.md) | No public IP, firewall/security-group rules for port 5432, peering and private endpoints, DNS |
| [ssl-tls.md](ssl-tls.md) | `verify-full` against a provider CA bundle, rotation, pooler/proxy hops |
| [secrets.md](secrets.md) | Secrets manager, injection, rotation patterns, short-lived credentials |
| [scaling.md](scaling.md) | Connection limits and pooling at scale, vertical vs horizontal, partitioning, when sharding is warranted |
| [deployment-checklist.md](deployment-checklist.md) | Scannable go-live checklist |

## Scope boundaries

- Core concepts here apply to any provider. Where a concept maps to a
  provider feature, the mapping is in the provider notes, not the body.
- Backups, PITR, and restore procedures live in
  [07-backups-recovery/](../07-backups-recovery/README.md). This module
  only states how they differ from HA.
- Role design, `pg_hba.conf`, and TLS server settings live in
  [06-security/](../06-security/README.md); the pages here add the
  cloud-network layer.
- Monitoring queries and alerts live in
  [14-observability/](../14-observability/README.md). Incident steps live
  in [15-production-runbooks/](../15-production-runbooks/README.md).

## Validation statement

No cloud account was available when this module was written. Provider
claims were checked against the providers' current official
documentation (dates in the provider notes), not executed against a live
service. SQL snippets were run on a local PostgreSQL 16 instance.

## Quick revision

- Database in a private subnet, no public IP, port 5432 open only to the
  app tier's security group/firewall rule.
- Pooler between app and primary; total connections budgeted.
- `sslmode=verify-full` with the provider CA bundle, not `prefer`.
- Credentials in a secrets manager; rotation rehearsed.
- HA, read replicas, and backups are three different tools.
- Failover is rehearsed with the real application and measured from the
  application side.
