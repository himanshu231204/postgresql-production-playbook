# Security

## What it is

How to restrict who can connect to PostgreSQL, what each connected role
can do, how credentials are stored and rotated, and how traffic is
encrypted in transit.

## Why it matters

A production database holds the data an attacker wants and is reachable
from every service that has a connection string. Most real incidents
come from a few repeating causes: an application connecting as a
superuser, a password committed to git, a database reachable from the
public internet without TLS, or an over-broad `GRANT`. This section
replaces those with explicit, auditable defaults.

## In this section

| Page | Covers |
|---|---|
| [roles.md](roles.md) | `CREATE ROLE`, login vs. group roles, role attributes, membership and inheritance |
| [permissions.md](permissions.md) | `GRANT`/`REVOKE`, the `PUBLIC` pseudo-role, `ALTER DEFAULT PRIVILEGES`, row-level security, auditing grants |
| [least-privilege.md](least-privilege.md) | The application / migration / administrator role split, with a complete setup script |
| [passwords-and-secrets.md](passwords-and-secrets.md) | SCRAM, `\password`, `.pgpass`, secrets managers, rotation |
| [ssl.md](ssl.md) | Server TLS, `pg_hba.conf` `hostssl`, client `sslmode`, verifying encryption |
| [security-checklist.md](security-checklist.md) | A scannable pre-production audit |

## Version notes

Examples target **PostgreSQL 16**. Behavior that differs by version is
labeled where it appears (notably PostgreSQL 14 for SCRAM as the default
password hash, PostgreSQL 15 for the `public` schema change, and
PostgreSQL 16 for `CREATEROLE` and role-membership changes).

## Where to go next

- Cloud network isolation, managed-service TLS, and cloud secrets
  managers: see [13-cloud-production/](../13-cloud-production/)
  ([networking.md](../13-cloud-production/networking.md),
  [secrets.md](../13-cloud-production/secrets.md),
  [ssl-tls.md](../13-cloud-production/ssl-tls.md)).
- Environment variables and secrets in containers: see
  [12-docker/environment-variables.md](../12-docker/environment-variables.md).
- Running migrations under the migration role: see
  [09-alembic/production-migrations.md](../09-alembic/production-migrations.md).
- Audit trails for agent state changes: see
  [11-agentic-ai/audit-logs.md](../11-agentic-ai/audit-logs.md).
- Connection exhaustion by a misbehaving client: see
  [15-production-runbooks/connection-exhaustion.md](../15-production-runbooks/connection-exhaustion.md).
