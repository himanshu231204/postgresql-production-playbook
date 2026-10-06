# Persistent Volumes

A container's filesystem is discarded with the container. PostgreSQL data
must live on a volume or bind mount, mounted at the path the image expects.

## Mount path by version

| PostgreSQL image | `PGDATA` | Declared `VOLUME` | Mount at |
|---|---|---|---|
| 17 and below | `/var/lib/postgresql/data` | `/var/lib/postgresql/data` | `/var/lib/postgresql/data` |
| 18 and above | `/var/lib/postgresql/<major>/docker` (e.g. `/var/lib/postgresql/18/docker`) | `/var/lib/postgresql` | `/var/lib/postgresql` |

Source: the official `postgres` image documentation ("Important Change"
under `PGDATA`). The 18+ layout lets `pg_upgrade --link` work across majors
when `/var/lib/postgresql` is mounted.

Mounting at the wrong path does not error. For 17 and below, mounting
`/var/lib/postgresql` instead of `.../data` leaves the declared `VOLUME`
unmounted, so Docker creates an **anonymous volume** and your data is not
reused after the container is recreated. Check with
`docker volume ls` for unexpected hashed volume names and
`docker inspect <container>` (Mounts section).

The example files mount at `/var/lib/postgresql/data` and pin
`postgres:16`. If you change the image to 18+, change the mount target
too. Do not point an existing PG 17 volume at an 18 image; follow a
`pg_upgrade` or dump/restore procedure.

## Named volume (default)

```yaml
services:
  db:
    image: postgres:16
    volumes:
      - pgdata:/var/lib/postgresql/data
volumes:
  pgdata:
```

Docker manages storage location and permissions; the entrypoint initializes
ownership for the `postgres` user. Works the same on Linux, macOS, and
Windows (where the volume lives inside the Docker VM, avoiding host
filesystem translation overhead).

## Bind mount

```yaml
volumes:
  - ./pgdata:/var/lib/postgresql/data
```

| Aspect | Named volume | Bind mount |
|---|---|---|
| Permissions | Handled by Docker/entrypoint | Host directory must be owned by the container's postgres UID (typically 999 on Debian images, 70 on Alpine; verify with `docker run --rm postgres:16 id postgres`) and mode `0700` |
| macOS / Windows performance | Good (inside the VM) | Slower through the host file-sharing layer; PostgreSQL's fsync-heavy I/O suffers |
| Data integrity | Normal | Windows/NTFS and some network filesystems can break PostgreSQL's file-permission and fsync assumptions; avoid |
| Host access to files | Via `docker volume inspect` path or helper container | Direct |
| Cleanup risk | `down -v` deletes it | Not removed by `down -v`; deleted by `rm -rf` |

Prefer named volumes for data. Use a bind mount when you must place data on
a specific host disk (Linux), after setting ownership explicitly.

## Lifecycle commands

All are **Docker commands**.

| Command | Purpose | Production Notes |
|---|---|---|
| `docker volume ls` | List volumes | Compose prefixes names with the project name (e.g. `pgplaybook-dev_pgdata`) |
| `docker volume inspect pgplaybook-dev_pgdata` | Show mountpoint, labels | Mountpoint is inside the Docker VM on macOS/Windows |
| `docker compose down` | Remove containers, keep volumes | Safe default |
| `docker compose down -v` | Remove containers and volumes | **DESTRUCTIVE: deletes the database.** Verify the project name and a restorable backup first |
| `docker volume rm <name>` | Delete one volume | **DESTRUCTIVE.** Fails if a container still uses it |
| `docker volume prune` | Delete unused volumes | **DESTRUCTIVE.** A stopped, removed database container leaves its volume "unused": prune deletes it. Do not run on production hosts |

## Re-initializing and init scripts

`/docker-entrypoint-initdb.d` scripts and `POSTGRES_*` bootstrap variables
run only when the data directory is empty. To re-run them locally:
`docker compose down -v && docker compose up -d` (destroys local data).

## Backups

A volume is not a backup: it is the same failure domain as the host.

```bash
# Unix shell: logical backup
docker compose exec -T db pg_dump -U app_admin -d appdb -Fc > appdb.dump
```

- Logical dumps: [07-backups-recovery/pg-dump.md](../07-backups-recovery/pg-dump.md),
  restore: [07-backups-recovery/pg-restore.md](../07-backups-recovery/pg-restore.md).
- Point-in-time recovery needs WAL archiving:
  [07-backups-recovery/point-in-time-recovery.md](../07-backups-recovery/point-in-time-recovery.md).
- Copying the raw volume contents while PostgreSQL runs yields an
  inconsistent backup. Stop the container first, or use `pg_basebackup`.
- Test restores into a scratch container: [15-production-runbooks/restore-database.md](../15-production-runbooks/restore-database.md).

## Production considerations

- Back the volume with storage suitable for databases: low-latency local or
  block storage, with snapshots and capacity monitoring. Network
  filesystems (NFS and similar) are a durability and locking risk.
- Monitor volume free space; a full disk stops PostgreSQL:
  [15-production-runbooks/disk-full.md](../15-production-runbooks/disk-full.md).
- Set `stop_grace_period` so the container is not killed mid-checkpoint.
- Major upgrades are a deliberate procedure (dump/restore or `pg_upgrade`),
  not an image tag change.
- Managed PostgreSQL removes the volume, backup, and failover burden at the
  cost of control; see [13-cloud-production/README.md](../13-cloud-production/README.md).

## Common mistakes

- Wrong mount path, producing an anonymous volume.
- Using `postgres:latest`; the layout and major version change under you.
- Bind mounting from a Windows or macOS host directory for a database that matters.
- Running `down -v` or `volume prune` on the wrong project.
- Treating the volume as the backup.

## Troubleshooting

| Symptom | Action |
|---|---|
| Data gone after recreate | Check mount path against the table; look for anonymous volumes |
| `data directory ... has wrong ownership` / `permissions` errors | Fix ownership to the postgres UID and mode `0700` on the bind-mounted directory |
| `database files are incompatible with server` | Volume was initialized by a different major version; restore from dump or use `pg_upgrade` |
| `initdb: directory exists but is not empty` (e.g. `lost+found`) | Mount a subdirectory, or set `PGDATA` to a subdirectory of the mount |

## Quick revision

- PG 17 and below: mount `/var/lib/postgresql/data`. PG 18+: mount `/var/lib/postgresql`.
- Named volume by default; bind mounts need explicit ownership.
- `down -v` and `volume prune` are destructive.
- Back up with `pg_dump` or PITR, not by trusting the volume.
