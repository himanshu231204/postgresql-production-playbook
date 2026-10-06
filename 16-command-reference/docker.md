# Docker Command Reference

**Docker commands** (`docker ...`, `docker compose ...`) run in your host
shell and act on containers. Anything after the container name runs
*inside* the container (`psql`, `pg_dump`, `pg_isready` are Unix shell
programs there). Compose file design, volumes, health checks and the
dev-versus-production split are in [12-docker/](../12-docker/)
([docker-compose.md](../12-docker/docker-compose.md),
[persistent-volumes.md](../12-docker/persistent-volumes.md),
[environment-variables.md](../12-docker/environment-variables.md)); this
page is the commands only.

Validation status: flags checked against `docker ... --help` output
(Docker Engine/CLI 29.x, Compose v5) and the Docker docs; **doc-verified,
not executed** (no Docker daemon was available). The `psql`, `pg_dump` and
`pg_isready` commands run inside the container were executed on Linux
outside Docker. Examples use fake names: container `pg`, compose service
`db`, image `postgres:16`.

## Run a container (development only)

```bash
docker run -d --name pg --restart unless-stopped \
  --env-file .env \
  -p 127.0.0.1:5432:5432 \
  -v pgdata:/var/lib/postgresql/data \
  postgres:16
```

| Piece | Purpose | Production notes |
|---|---|---|
| `-d` | Detached | |
| `--name pg` | Stable name for later commands | |
| `--env-file .env` | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` from a git-ignored file | The official image refuses to initialize without `POSTGRES_PASSWORD` (or an explicit trust setting). Never put the value on the command line or in an image |
| `-p 127.0.0.1:5432:5432` | Publish bound to localhost | `-p 5432:5432` exposes the port on every host interface: avoid on shared hosts |
| `-v pgdata:/var/lib/postgresql/data` | Named volume for data | Data lives in the volume, not the container. Mount path is for PostgreSQL 16 images; newer images change it, so check the image documentation for your tag |
| `postgres:16` | Pin a major version | Do not use `latest`: a major upgrade needs `pg_upgrade` or dump/restore |

`.env.example` (committed) holds placeholders only:

```text
POSTGRES_USER=app_admin
POSTGRES_PASSWORD=CHANGE_ME
POSTGRES_DB=appdb
```

## Run commands inside the container

| Task | `docker` | `docker compose` | Notes |
|---|---|---|---|
| Interactive `psql` | `docker exec -it pg psql -U USER -d DBNAME` | `docker compose exec db psql -U USER -d DBNAME` | `-i` keeps stdin open, `-t` allocates a TTY |
| `psql` using the container's own env vars | `docker exec -it pg sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'` | `docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'` | Single quotes so the variable expands inside the container, not on your host |
| One command | `docker exec pg psql -U USER -d DBNAME -c "SELECT 1;"` | `docker compose exec -T db psql -U USER -d DBNAME -c "SELECT 1;"` | `-T` disables the TTY: required in CI and pipes |
| Run a SQL file from the host | `docker exec -i pg psql -U USER -d DBNAME -v ON_ERROR_STOP=1 < migration.sql` | `docker compose exec -T db psql -U USER -d DBNAME -v ON_ERROR_STOP=1 < migration.sql` | `-i` (no `-t`) so stdin passes through. In PowerShell `<` is unsupported: copy the file in with `docker cp`, then `-f` |
| Readiness check | `docker exec pg pg_isready -U USER -d DBNAME` | `docker compose exec -T db pg_isready -U USER -d DBNAME` | Exit 0 when accepting connections |
| Shell in the container | `docker exec -it pg bash` | `docker compose exec db bash` | |
| Run as a specific user | `docker exec -u postgres pg ...` | `docker compose exec -u postgres db ...` | `-u` / `--user` |
| Connect from the host | `psql -h 127.0.0.1 -p 5432 -U USER -d DBNAME` | same | Needs the published port; client tools on the host |

`psql` meta-commands work the same inside: `docker exec -it pg psql -U USER -d DBNAME -c '\dt'` (see [psql.md](psql.md)).

## Backup and restore through a container

```bash
# Dump inside the container, copy the file out
docker exec pg pg_dump -U USER -d DBNAME -Fc -f /tmp/appdb.dump
docker cp pg:/tmp/appdb.dump ./appdb.dump

# Restore: copy in, restore into a NEW database
docker cp ./appdb.dump pg:/tmp/appdb.dump
docker exec pg createdb -U USER appdb_restore
docker exec pg pg_restore -U USER -d appdb_restore --no-owner /tmp/appdb.dump
```

Expected: no output on success. Use `-f` plus `docker cp`; redirecting
binary output with `docker exec ... > file` can be corrupted by a TTY (omit
`-t`) or by PowerShell 5.1's `>` encoding. Flags: [pg-dump.md](pg-dump.md),
[pg-restore.md](pg-restore.md). Volume snapshots are not a substitute for a
tested logical or physical backup:
[07-backups-recovery/](../07-backups-recovery/).

## Inspect, logs, lifecycle

| Task | `docker` | `docker compose` | Production notes |
|---|---|---|---|
| List containers | `docker ps` (`-a` for stopped) | `docker compose ps` | |
| Follow logs | `docker logs -f --tail 100 pg` | `docker compose logs -f --tail 100 db` | `--since 10m` limits the window. Read before restarting |
| Health status | `docker inspect --format '{{.State.Health.Status}}' pg` | `docker compose ps` | Only meaningful if the image/compose defines a health check, e.g. `pg_isready` ([12-docker/docker-compose.md](../12-docker/docker-compose.md)) |
| Start / stop | `docker start pg` / `docker stop -t 60 pg` | `docker compose start db` / `docker compose stop db` | `stop` signals the container's stop signal (the official image uses SIGINT, a fast shutdown), then SIGKILL after `-t` seconds; give a generous `-t` so it can checkpoint first |
| Restart | `docker restart pg` | `docker compose restart db` | Drops all connections |
| Create/start stack | n/a | `docker compose up -d` (`--wait` blocks until healthy) | |
| Config check | n/a | `docker compose config` | Validates and prints the resolved file: use before committing |
| List volumes | `docker volume ls` | n/a | |

## Destructive Docker commands

| Command | What it does | Why risky | Precaution / alternative |
|---|---|---|---|
| `docker compose down -v` | Removes containers **and named volumes** | Deletes the database files | Plain `docker compose down` keeps volumes; back up first (above) |
| `docker volume rm pgdata` | Deletes the volume | Irreversible data loss | `docker volume ls`, confirm no container uses it, back up |
| `docker rm -f pg` | Kills and removes the container | SIGKILL: crash recovery on next start; with `-v`, anonymous volumes go too | `docker stop -t 60 pg`, then `docker rm pg` |
| `docker run ... -v pgdata:/var/lib/postgresql/data` on a *different* major version image | Starts an old data directory with a newer server | Server refuses to start (version mismatch) | Dump/restore or `pg_upgrade` |
| `docker system prune --volumes` | Removes unused volumes | Silently deletes a stopped project's data volume | Avoid on any host with PostgreSQL data |

Containers for **local development and CI**. Production PostgreSQL in
containers needs tested backups, restore drills, resource limits, a
supervised orchestrator and an upgrade plan; or a managed service
([13-cloud-production/](../13-cloud-production/)).

## Troubleshooting

| Symptom | Check | Fix |
|---|---|---|
| Container exits immediately | `docker logs pg` | Usually missing `POSTGRES_PASSWORD`, or a data directory from another major version |
| `psql: ... Connection refused` from host | `docker ps` (port column), `docker logs pg` | Publish the port; wait for readiness (`pg_isready`): startup initialization takes seconds |
| `role "USER" does not exist` | Env vars are applied only when the data directory is first initialized | Create the role with SQL, or recreate the volume if disposable |
| `the input device is not a TTY` | `-t` used in a pipe/CI | Drop `-t` (`docker exec -i`) or use `compose exec -T` |
| Env var empty inside `exec` command | Host shell expanded it | Wrap in `sh -c '...'` with single quotes |
| Host port already in use | `lsof -nP -iTCP:5432 -sTCP:LISTEN` ([macos.md](macos.md), [linux.md](linux.md)) or `netstat -ano \| findstr 5432` ([windows.md](windows.md)) | Map another host port, e.g. `-p 127.0.0.1:5433:5432` |

## Quick revision

- `docker exec -it pg psql -U USER -d DB`; `docker compose exec -T db ...` in scripts.
- `docker logs -f --tail 100 pg` before restarting.
- Named volume for `/var/lib/postgresql/data`; `down -v` and `volume rm` delete data.
- Secrets via git-ignored `.env`, not the command line or image.
- Pin the major version tag; bind the port to `127.0.0.1` for local work.
