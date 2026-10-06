# Docker Compose

Syntax is Compose v2 (`docker compose`, not the legacy `docker-compose`
binary). Do not add the top-level `version:` key; Compose treats it as
obsolete and ignores it. Files: [examples/compose.dev.yaml](examples/compose.dev.yaml),
[examples/compose.prod-like.yaml](examples/compose.prod-like.yaml).

## Commands

All are **Docker commands** (run in a Unix shell, PowerShell, or CMD; syntax is identical).

| Command | Purpose | Production Notes |
|---|---|---|
| `docker compose -f compose.dev.yaml config` | Validate and print the resolved file | Run before every deploy; shows interpolated values, so it can print secrets from `.env` |
| `docker compose -f compose.dev.yaml up -d` | Create and start services detached | Re-running with a changed image recreates the container; the named volume is kept |
| `docker compose ps` | Show state and health | `healthy` requires a `healthcheck` |
| `docker compose logs -f db` | Follow PostgreSQL logs | Set `log_min_duration_statement` to surface slow queries |
| `docker compose exec db psql -U app_admin -d appdb` | Open `psql` in the container | Unix-socket `trust` auth applies inside the container only |
| `docker compose stop` / `down` | Stop / remove containers and network | Volumes are kept |
| `docker compose down -v` | Remove containers **and named volumes** | **DESTRUCTIVE** (see below) |

Expected result of `up -d` on a fresh volume: `db` shows `starting`, then
`healthy` after initialization.

## Example

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: ${POSTGRES_USER:?set POSTGRES_USER in .env}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD in .env}
      POSTGRES_DB: ${POSTGRES_DB:?set POSTGRES_DB in .env}
    ports:
      - "127.0.0.1:5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    shm_size: 256mb
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -h 127.0.0.1 -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 5s
      timeout: 5s
      retries: 10
      start_period: 20s
  app:
    build: .
    depends_on:
      db:
        condition: service_healthy
volumes:
  pgdata:
```

- `${VAR:?message}` aborts if the variable is unset or empty.
- `$$` escapes `$` so the container shell expands the variable, not Compose.
- The `-h 127.0.0.1` flag forces a TCP check. During first-time
  initialization the image runs a temporary server that listens only on the
  Unix socket, so a socket-based `pg_isready` can report ready before the
  real server accepts network connections.

## Readiness: `depends_on`

`depends_on` alone only orders container start. Use
`condition: service_healthy` to wait for the `healthcheck`. `pg_isready`
reports whether the server accepts connections; it does not verify
credentials or that migrations ran. Applications still need connection
retry logic. See [14-observability/health-checks.md](../14-observability/health-checks.md).

## `down` vs `down -v`

> **DESTRUCTIVE: `docker compose down -v` deletes the named volumes in the
> project, including the database.** Without a backup, the data is gone.
> Before running it: confirm the project (`docker compose ls`), the volume
> list (`docker volume ls`), and that a verified dump exists
> ([07-backups-recovery/pg-dump.md](../07-backups-recovery/pg-dump.md)).
> Safer alternative: `docker compose down` (keeps volumes) or `stop`.

`down -v` is the correct way to reset a local database so
`/docker-entrypoint-initdb.d` scripts run again. Do not run it against
anything you cannot recreate.

## Ports and networking

- `"127.0.0.1:5432:5432"` publishes on loopback only. `"5432:5432"` binds
  all host interfaces and, depending on host firewall rules, exposes the
  database to the network.
- Services on the same Compose network reach `db:5432` by service name; no
  published port is needed for app-to-database traffic. Omit `ports:` for
  the database in production-like setups.
- `networks: backend: internal: true` blocks external egress and ingress for
  that network. Attach the app to a second, non-internal network if it needs
  outbound access or published ports.
- Add TLS for any connection that leaves the host; see
  [06-security/ssl.md](../06-security/ssl.md).

## PostgreSQL configuration

Pass parameters on the `command`:

```yaml
command: ["postgres", "-c", "max_connections=100", "-c", "shared_buffers=512MB"]
```

Or mount a file and point the server at it (from the image documentation):

```yaml
command: ["postgres", "-c", "config_file=/etc/postgresql/postgresql.conf"]
volumes:
  - ./postgresql.conf:/etc/postgresql/postgresql.conf:ro
```

The values in the example files are illustrative starting points, not
tuned recommendations. Setting `config_file` replaces the default file in
the data directory, so the mounted file must contain every setting you need.

`shm_size`: the container default for `/dev/shm` is 64MB. If exhausted,
queries fail with `could not resize shared memory segment ... No space left
on device`. Set `shm_size` (the example uses `256mb`).

## Production usage: `compose.prod-like.yaml`

Differences from the dev file: password via `POSTGRES_PASSWORD_FILE` and a
Compose `secrets:` file, no published port, an internal network,
`stop_grace_period: 60s` for a clean shutdown, and `POSTGRES_INITDB_ARGS:
"--data-checksums"` (applies at first initialization only). It still has no
HA, no automated backups, and no monitoring. Treat it as a staging or
small single-host reference.

## pgbouncer sidecar (optional)

| Benefit | Cost |
|---|---|
| Caps real PostgreSQL connections while serving many clients | Extra container to run, monitor, and secure |
| Keeps `max_connections` modest | Transaction pooling breaks session state (`SET`, advisory locks, some prepared-statement usage) |
| Absorbs connection storms from many workers | Adds a network hop; credentials must be configured in the pooler too |

Pool mode details: [05-performance/connection-pooling.md](../05-performance/connection-pooling.md).
Use an image you have vetted and pin its tag.

## Backups from a container

```bash
# Unix shell. Custom-format dump to the host; -T disables TTY so the binary stream is not corrupted.
docker compose exec -T db pg_dump -U app_admin -d appdb -Fc > appdb_$(date +%F).dump
```

Run the dump as a role with read access, store it off the volume's host,
and test restores: [07-backups-recovery/pg-dump.md](../07-backups-recovery/pg-dump.md),
[07-backups-recovery/pg-restore.md](../07-backups-recovery/pg-restore.md).
A volume copy of a running database is not a consistent backup.

## Common mistakes

- Missing `condition: service_healthy`; app crashes on first boot.
- Editing `POSTGRES_PASSWORD` in compose after first start and expecting
  the role password to change. It is applied only at initialization; use
  `\password` or `ALTER ROLE` instead.
- Publishing `5432` publicly with a weak password.
- Running `down -v` out of habit.
- Defining a top-level `version:` key.

## Troubleshooting

| Symptom | Cause / action |
|---|---|
| `password authentication failed` after changing the env var | Volume already initialized; change the role password in SQL or recreate the volume (destroys data) |
| Init scripts did not run | Data directory was not empty; see [environment-variables.md](environment-variables.md) |
| `could not resize shared memory segment` | Raise `shm_size` |
| `port is already allocated` | Another process uses 5432; change the host side, e.g. `127.0.0.1:5433:5432` |
| Container restarts repeatedly | `docker compose logs db`; check the volume mount path and permissions: [persistent-volumes.md](persistent-volumes.md) |
| Disk filling | [15-production-runbooks/disk-full.md](../15-production-runbooks/disk-full.md) |

## Quick revision

- `docker compose`, no `version:`; pin `postgres:<major>`.
- `healthcheck` with `pg_isready` plus `depends_on: condition: service_healthy`.
- `127.0.0.1:5432:5432` for dev; no published port for production-like.
- `down -v` is destructive.
