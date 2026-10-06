# Passwords and Secrets

## What it is

How database credentials are hashed on the server, entered without
leaking, stored by clients, and rotated.

## Why it matters

Credentials leak through shell history, logs, `ps` output, committed
`.env` files, container image layers, and error messages. A leaked
`DATABASE_URL` is a full login for the role it names.

## Server-side hashing

PostgreSQL stores a hash, not the password. Use SCRAM:

```
# postgresql.conf (PostgreSQL 14+ default)
password_encryption = scram-sha-256
```

```
# pg_hba.conf: require SCRAM for password logins
host    appdb    app_api    10.0.0.0/8    scram-sha-256
```

- `scram-sha-256` has been available since PostgreSQL 10 and is the
  default for `password_encryption` since **PostgreSQL 14**.
- `md5` is deprecated (PostgreSQL 18 officially deprecates it); avoid for
  new roles. Passwords stored as MD5 hashes stay MD5 until the role's
  password is set again under `password_encryption = scram-sha-256`.
- Never use `trust` in `pg_hba.conf` for a network-reachable address.
- Client drivers must support SCRAM (libpq 10+, asyncpg and psycopg do).

## Setting a password

| Method | Type | Notes |
|---|---|---|
| `\password app_api` | psql meta-command | Prompts twice, hashes client-side before sending; the cleartext does not appear in server logs. Preferred for interactive use. |
| `ALTER ROLE app_api PASSWORD 'value';` | PostgreSQL SQL | The statement text may appear in server logs (`log_statement`), `pg_stat_activity`, and shell/psql history. Avoid for real credentials. |

Run `\password` as the role itself or as an admin with the target
role name. Expected result: no output; the next login uses the new
password.

## Client-side storage

| Mechanism | Platform | Notes |
|---|---|---|
| `~/.pgpass` | Unix shell (macOS/Linux) | Lines `host:port:database:user:password`. Must be `chmod 0600`; libpq ignores it otherwise. |
| `%APPDATA%\postgresql\pgpass.conf` | Windows | Same format; Windows does not enforce permissions the same way, so rely on directory ACLs. |
| `PGPASSFILE` | Both | Points libpq at a non-default password file. |
| `PGPASSWORD` | Both | Environment variable. Discouraged by the PostgreSQL docs: environment can be visible to other users on some systems. Acceptable inside a short-lived container with a secrets manager injecting it. |
| `~/.pg_service.conf` | Unix shell | Connection service names; can reference `passfile`. |

```bash
# Unix shell
printf '%s\n' 'db.internal:5432:appdb:app_api:REPLACE_WITH_REAL_PASSWORD' >> ~/.pgpass
chmod 0600 ~/.pgpass
psql "host=db.internal dbname=appdb user=app_api sslmode=verify-full"
```

## Application secrets

BAD — hardcoded in source:

```python
engine = create_async_engine("postgresql+asyncpg://app_api:hunter2@db/appdb")
```

GOOD — read from the environment, injected by a secrets manager or
orchestrator:

```python
import os

DATABASE_URL: str = os.environ["DATABASE_URL"]
```

`.env.example` (committed, placeholders only):

```
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:5432/DATABASE
```

- Add `.env` to `.gitignore`. If a real secret was ever committed,
  rotate it; deleting the commit does not un-leak it.
- Docker: do not use `ENV`/`ARG` for secrets in a `Dockerfile` (they
  persist in image layers/metadata). Pass them at runtime or use Docker
  secrets. See
  [12-docker/environment-variables.md](../12-docker/environment-variables.md).
- Cloud: use the provider's secrets manager and, where offered,
  short-lived or IAM-based database credentials. See
  [13-cloud-production/secrets.md](../13-cloud-production/secrets.md).
- Mask `DATABASE_URL` in logs and error reporting; connection strings
  embed the password.

## Rotation without downtime

1. Create a second login role (`app_api_v2`, same group membership) or
   change the password in a way both versions of the app can tolerate.
2. Update the secret in the secrets manager; roll the application so
   every instance picks it up.
3. Confirm no connections use the old role/credential: `SELECT usename,
   count(*) FROM pg_stat_activity GROUP BY usename;`
4. Remove the old credential: `ALTER ROLE app_api_old NOLOGIN;` first
   (reversible), then drop later.

Changing a password with `ALTER ROLE` does not terminate existing
sessions; they continue until they reconnect. Pools will fail on their
next new connection if the app has not picked up the new value.

## Common mistakes

- Putting a real password in `docker-compose.yml`, a CI log, or a
  screenshot.
- Using `PGPASSWORD=... psql` on a shared host.
- Reusing one password across dev, staging, and production.
- Assuming `ALTER ROLE ... PASSWORD` kicks existing sessions off.

## Quick revision

- `scram-sha-256` for hashing and `pg_hba.conf`; no `trust`.
- Set passwords with `\password`, not `ALTER ROLE ... PASSWORD '...'`.
- Secrets come from the environment or a secrets manager; commit only `.env.example`.
- Rotate by overlapping credentials, then retire the old one.
