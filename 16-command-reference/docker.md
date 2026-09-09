# Docker Command Reference

Commands for running and operating a PostgreSQL container. For Dockerfile
design, `docker-compose.yml` structure, volumes, and healthchecks, see
[12-docker/](../12-docker/) — this page is the flat command lookup.

## Running a container

```bash
docker run --name pg -e POSTGRES_PASSWORD=changeme -p 5432:5432 -d postgres:16
```

`POSTGRES_PASSWORD` is required by the official image on first startup.
Never hardcode a real password here in a script or compose file committed
to version control — use an env file or secrets manager; see
[06-security/passwords-and-secrets.md](../06-security/passwords-and-secrets.md)
and [12-docker/environment-variables.md](../12-docker/environment-variables.md).

## `docker compose`

| Task | Command | Notes |
|---|---|---|
| Start (detached) | `docker compose up -d` | |
| Stop, keep volumes | `docker compose stop` | |
| Stop and remove containers | `docker compose down` | Named volumes survive by default |
| Stop and remove containers **and volumes** | `docker compose down -v` | **Destructive** — deletes the database's persistent data |
| View logs | `docker compose logs -f postgres` | Replace `postgres` with the service name in your compose file |
| Rebuild after a Dockerfile change | `docker compose up -d --build` | |

## Connecting to a running container

```bash
docker exec -it pg psql -U postgres
```

`-it` allocates an interactive TTY, needed for `psql`'s interactive
prompt. Without it, `psql` will fail or behave as if piped.

## Inspecting containers and volumes

| Task | Command |
|---|---|
| List running containers | `docker ps` |
| List all containers (including stopped) | `docker ps -a` |
| Follow a container's logs | `docker logs -f pg` |
| List volumes | `docker volume ls` |
| Inspect a volume (find its actual path on the host) | `docker volume inspect VOLUME_NAME` |
| Check container health status | `docker inspect --format='{{.State.Health.Status}}' pg` |

## Copying files in/out (backup/restore via Docker)

```bash
# Dump from inside the container to the host
docker exec pg pg_dump -U postgres -F c -f /tmp/app_db.dump app_db
docker cp pg:/tmp/app_db.dump ./app_db.dump

# Restore: copy in, then run pg_restore inside the container
docker cp ./app_db.dump pg:/tmp/app_db.dump
docker exec pg pg_restore -U postgres -d app_db /tmp/app_db.dump
```

## Common mistakes

- Running `docker compose down -v` thinking it only stops the stack — the
  `-v` flag also deletes the named volume, and with it the database's data.
- Forgetting `-it` on `docker exec` and getting a confusing failure from
  `psql` instead of an interactive session.
- Storing `POSTGRES_PASSWORD` directly in a `docker-compose.yml` that gets
  committed to version control. Use an `.env` file (git-ignored) or a
  secrets manager instead.

## Production considerations

Running PostgreSQL itself in a plain Docker container (rather than a
managed service or an orchestrated stateful workload) needs a real backup
strategy independent of the container — a container restart or removal
without a durable named volume loses all data. See
[12-docker/persistent-volumes.md](../12-docker/persistent-volumes.md) and
[07-backups-recovery/](../07-backups-recovery/).
