# Environment Variables

Configuration of the official `postgres` image and of application
containers. Source: the Docker Official Image documentation for `postgres`.
Template: [examples/.env.example](examples/.env.example).

## `postgres` image variables

| Variable | Purpose | Notes |
|---|---|---|
| `POSTGRES_PASSWORD` | Superuser password | Required (unless `POSTGRES_HOST_AUTH_METHOD=trust`); must not be empty |
| `POSTGRES_USER` | Superuser name | Default `postgres`; this role is a **superuser** |
| `POSTGRES_DB` | Default database name | Default is the value of `POSTGRES_USER` |
| `POSTGRES_INITDB_ARGS` | Extra arguments to `initdb` | e.g. `--data-checksums`; space-separated |
| `POSTGRES_INITDB_WALDIR` | Separate WAL directory | Initialization only |
| `POSTGRES_HOST_AUTH_METHOD` | `pg_hba.conf` method for `host` connections | Default `scram-sha-256` on 14+. Avoid `trust` |
| `PGDATA` | Data directory | Set by the image; see [persistent-volumes.md](persistent-volumes.md) |

These bootstrap variables take effect **only when the container starts with
an empty data directory.** On an existing volume they are ignored: changing
`POSTGRES_PASSWORD` later does not change the role's password. Use
`\password` (psql meta-command) or `ALTER ROLE`.

`/docker-entrypoint-initdb.d` scripts follow the same rule.

## `_FILE` variants and Docker secrets

Appending `_FILE` makes the entrypoint read the value from a file. Supported
for `POSTGRES_INITDB_ARGS`, `POSTGRES_PASSWORD`, `POSTGRES_USER`, and
`POSTGRES_DB`.

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: app_admin
      POSTGRES_PASSWORD_FILE: /run/secrets/postgres_password
    secrets:
      - postgres_password

secrets:
  postgres_password:
    file: ./secrets/postgres_password.txt   # git-ignored
```

- The password is not visible in `docker inspect` environment output or in
  `docker compose config` as a literal value.
- The file must be readable by the process user in the container (the
  `postgres` user; check with `docker run --rm postgres:16 id postgres`).
- Generate the file with a restrictive `umask`; never commit it.
- Applies only at initialization, same as `POSTGRES_PASSWORD`.

Compose file-based secrets are mounted into the container as files. A
secrets manager or orchestrator (Swarm, Kubernetes, cloud) can supply the
same file. See [13-cloud-production/secrets.md](../13-cloud-production/secrets.md).

## Where variables come from

| Source | Visible via | Notes |
|---|---|---|
| `environment:` in compose | `docker inspect`, `docker compose config` | Literal values here are committed values; use `${VAR}` interpolation |
| `.env` next to the compose file | Interpolation only (not passed to containers unless referenced) | Git-ignored; commit `.env.example` |
| `env_file:` | `docker inspect` | Passes every entry into the container |
| `docker run -e` / `--env-file` | Shell history, `docker inspect` | Prefer `--env-file` |
| `*_FILE` + secrets | File inside container | Not in container environment |

Environment variables are visible to anyone who can run `docker inspect` on
the host, and are inherited by child processes. For the application,
`DATABASE_URL` as an env var is common and acceptable when injected by an
orchestrator; for the superuser password prefer `_FILE`.

## BAD vs GOOD

```yaml
# BAD: literal secret in a committed file
environment:
  POSTGRES_PASSWORD: hunter2
```

```yaml
# GOOD: interpolated from a git-ignored .env, fails loudly if missing
environment:
  POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD in .env}
```

```dockerfile
# BAD: ENV/ARG secrets persist in image layers and metadata
ENV DATABASE_URL=postgresql://USER:real-password@db/appdb
```

## `.env.example`

```bash
POSTGRES_IMAGE=postgres:16
POSTGRES_USER=app_admin
POSTGRES_DB=appdb
POSTGRES_PASSWORD=REPLACE_WITH_LOCAL_DEV_PASSWORD
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@db:5432/DATABASE
```

Add `.env` to `.gitignore`. The repository root had no `.gitignore` when
this page was written; [examples/.gitignore](examples/.gitignore) covers
`.env` and `secrets/` for the example folder only.

If a real secret was ever committed, rotate it. Deleting the commit does
not un-leak it. Rotation steps:
[06-security/passwords-and-secrets.md](../06-security/passwords-and-secrets.md).

## Locale and encoding

Choose at initialization: `POSTGRES_INITDB_ARGS="--encoding=UTF8 --locale-provider=icu --icu-locale=en-US"`
(provider options need PostgreSQL 15+). Changing it later requires a
dump and restore into a new cluster.

## Common mistakes

- Changing `POSTGRES_PASSWORD` or `POSTGRES_DB` on an initialized volume.
- `POSTGRES_HOST_AUTH_METHOD=trust` left enabled outside local tests.
- Using the superuser (`POSTGRES_USER`) as the application login.
- `env_file: .env` passing unrelated secrets to every service.
- Printing `docker compose config` output in CI logs with real values.

## Quick revision

- `POSTGRES_*` apply once, to an empty data directory.
- `POSTGRES_PASSWORD_FILE` + secret file beats a literal env value.
- `.env` ignored, `.env.example` committed, never `ENV`/`ARG` secrets.
