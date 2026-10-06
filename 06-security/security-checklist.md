# Security Checklist

A scannable audit for a PostgreSQL deployment. Each item links to the
page that explains it.

## Access

- [ ] The application connects as a dedicated, non-superuser role — see
      [roles.md](roles.md).
- [ ] Application, migration, and admin credentials are different roles
      — see [least-privilege.md](least-privilege.md).
- [ ] `PUBLIC` has no `CONNECT` on the database and no `CREATE` on any
      schema — see [permissions.md](permissions.md#the-public-pseudo-role).
- [ ] The application role has no `TRUNCATE`, `REFERENCES`, `TRIGGER`,
      or DDL — see [permissions.md](permissions.md#auditing-existing-grants).
- [ ] Per-role `statement_timeout` and
      `idle_in_transaction_session_timeout` are set where appropriate.
- [ ] Per-role `CONNECTION LIMIT` is consistent with pool size — see
      [05-performance/connection-pooling.md](../05-performance/connection-pooling.md).
- [ ] No role has `BYPASSRLS`, `CREATEROLE`, or `SUPERUSER` unless it is
      a named admin role.

## Authentication

- [ ] `password_encryption = scram-sha-256`; no `md5` or `trust` lines in
      `pg_hba.conf` for network addresses — see
      [passwords-and-secrets.md](passwords-and-secrets.md#server-side-hashing).
- [ ] `pg_hba.conf` addresses are narrow (specific CIDR ranges), and
      `pg_hba_file_rules` shows no errors.
- [ ] Passwords set with `\password`, not in SQL scripts or history.

## Network and encryption

- [ ] `listen_addresses` is not exposed to the public internet; access
      is limited by firewall/security group — see
      [13-cloud-production/networking.md](../13-cloud-production/networking.md).
- [ ] `ssl = on`, `hostssl` rules, and `hostnossl ... reject` — see
      [ssl.md](ssl.md).
- [ ] Clients use `sslmode=verify-full`; `pg_stat_ssl` shows no
      unencrypted client sessions.
- [ ] Certificate expiry is monitored.

## Secrets

- [ ] No credentials in git history, `Dockerfile`, or `docker-compose.yml`;
      `.env` is git-ignored; `.env.example` has placeholders only — see
      [12-docker/environment-variables.md](../12-docker/environment-variables.md).
- [ ] Secrets come from a secrets manager or injected environment — see
      [13-cloud-production/secrets.md](../13-cloud-production/secrets.md).
- [ ] A rotation procedure exists and has been exercised.
- [ ] Connection strings are masked in logs and error reports.

## Data and operations

- [ ] Backups exist, are encrypted at rest, and restore has been tested —
      see [07-backups-recovery/](../07-backups-recovery/).
- [ ] Application queries are parameterized; no string-formatted SQL.
- [ ] LLM- or user-generated values are validated before reaching a write
      path — see [11-agentic-ai/tool-calls.md](../11-agentic-ai/tool-calls.md).
- [ ] Sensitive state changes are auditable — see
      [11-agentic-ai/audit-logs.md](../11-agentic-ai/audit-logs.md).
- [ ] Connection and authentication failures are logged (`log_connections`,
      `log_disconnections`) and reviewed; statement logging does not
      capture sensitive literals.

## Quick triage query

Run as an admin to list roles with elevated attributes:

```sql
SELECT rolname, rolsuper, rolcreaterole, rolcreatedb, rolreplication, rolbypassrls
FROM pg_roles
WHERE rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls
ORDER BY rolname;
```

Every row should be a role you can name and justify.
