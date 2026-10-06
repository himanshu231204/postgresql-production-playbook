# Linux Command Reference

All commands here are **Unix shell** (bash/zsh) commands unless marked
`psql` or SQL. Service and unit names differ by distribution and packaging,
so identify yours before copying.

Validation status: `pg_lsclusters`, `pg_ctl`, `pg_isready`, `lsof`, `nc`,
`ps`, `psql` were executed on Ubuntu 24.04 with PostgreSQL 16.
`systemctl`, `journalctl`, `ss`, `pg_ctlcluster` and the RHEL commands are
documentation-verified, not executed. Cross-OS comparison:
[README.md](README.md).

## Which flavor am I on?

| | Debian / Ubuntu (`postgresql-common`) | RHEL / Rocky / Alma / Fedora (PGDG packages) |
|---|---|---|
| Service unit | `postgresql@16-main` (per cluster); `postgresql.service` is an umbrella unit | `postgresql-16` |
| Binaries | `/usr/lib/postgresql/16/bin` (wrappers like `psql` are on `PATH`) | `/usr/pgsql-16/bin` (add to `PATH`) |
| Data directory | `/var/lib/postgresql/16/main` | `/var/lib/pgsql/16/data` |
| Config | `/etc/postgresql/16/main/postgresql.conf`, `pg_hba.conf` | in the data directory |
| Log | `/var/log/postgresql/postgresql-16-main.log` and journal | journal, and `log/` in the data directory if `logging_collector` is on |
| First-time init | cluster created on install (`pg_lsclusters`) | `sudo /usr/pgsql-16/bin/postgresql-16-setup initdb` |
| Run as the OS user | `sudo -u postgres psql` | `sudo -u postgres psql` |

Check what exists: `systemctl list-units 'postgresql*'` and
`pg_lsclusters` (Debian family only). Do not hard-code `16`; substitute
your major version. Official Linux packages: https://www.postgresql.org/download/linux/.

## Service control

| Task | Debian / Ubuntu | RHEL family | Production Notes |
|---|---|---|---|
| List units | `systemctl list-units 'postgresql*'` | same | |
| List clusters | `pg_lsclusters` | n/a | Shows version, cluster, port, status, data dir, log file |
| Status | `systemctl status postgresql@16-main` | `systemctl status postgresql-16` | `systemctl status postgresql` (umbrella) reports "active (exited)" even if no cluster runs |
| Start | `sudo systemctl start postgresql@16-main` | `sudo systemctl start postgresql-16` | |
| Stop | `sudo systemctl stop postgresql@16-main` | `sudo systemctl stop postgresql-16` | Fast shutdown: rolls back open transactions and disconnects clients |
| Restart | `sudo systemctl restart postgresql@16-main` | `sudo systemctl restart postgresql-16` | Drops all connections; apps/poolers must reconnect. Maintenance window |
| Reload config | `sudo systemctl reload postgresql@16-main` | `sudo systemctl reload postgresql-16` | Applies `pg_hba.conf` and reloadable settings without dropping sessions. Reloading the Debian umbrella unit `postgresql` does nothing (its `ExecReload` is `/bin/true`) |
| Enable at boot | `sudo systemctl enable postgresql` | `sudo systemctl enable postgresql-16` | |
| Cluster-level wrapper (Debian) | `sudo pg_ctlcluster 16 main start\|stop\|restart\|reload\|status` | n/a | Same actions through `postgresql-common` |
| Direct `pg_ctl` | `sudo -u postgres /usr/lib/postgresql/16/bin/pg_ctl -D DATADIR status` | `sudo -u postgres /usr/pgsql-16/bin/pg_ctl -D DATADIR status` | Use for non-packaged instances. Default stop mode is `fast`; `-m immediate` forces crash recovery on next start: last resort |

`pg_ctl` actions: `start`, `stop`, `restart`, `reload`, `status`,
`promote`, `logrotate`. Do not run `pg_ctl` against a data directory that
systemd also manages.

## Logs

| Command | Purpose | Notes |
|---|---|---|
| `journalctl -u postgresql@16-main -f` | Follow the Debian cluster's log | RHEL: `journalctl -u postgresql-16 -f` |
| `journalctl -u postgresql@16-main --since "30 min ago"` | Recent window | |
| `sudo tail -f /var/log/postgresql/postgresql-16-main.log` | Debian log file | |
| `journalctl -u postgresql@16-main -p err` | Errors only | |

Read the log before restarting: the cause of an outage is usually already
there. See [15-production-runbooks/database-is-down.md](../15-production-runbooks/database-is-down.md).

## Network checks

| Command | Purpose | Expected / notes |
|---|---|---|
| `ss -ltnp \| grep 5432` | Who is listening on TCP 5432 | Needs `sudo` to show process names. Listening only on `127.0.0.1` means `listen_addresses` excludes remote clients |
| `lsof -nP -iTCP:5432 -sTCP:LISTEN` | Same, via `lsof` | Output shows `postgres ... TCP 127.0.0.1:5432 (LISTEN)` |
| `ps -ef \| grep '[p]ostgres'` | Server processes | The first line shows `-D DATADIR` and port |
| `nc -zv HOST 5432` | TCP reachability | `succeeded!` means the port is open, not that PostgreSQL authenticates you |
| `pg_isready -h HOST -p 5432` | Server accepting connections | `HOST:5432 - accepting connections`; exit 0 |
| `sudo ss -ltnp 'sport = :5432'` | Filter form | |

Firewall: open 5432 only to application subnets; prefer private
networking ([13-cloud-production/](../13-cloud-production/)).

## Environment variables and passwords

```bash
export PGHOST=HOST PGPORT=5432 PGUSER=app_rw PGDATABASE=appdb PGSSLMODE=require
psql -X -c "SELECT current_user, current_database();"
```

Persist in `~/.bashrc` / `~/.zshrc` only non-secret values. Passwords go in
`~/.pgpass`, mode `0600`:

```bash
printf '%s\n' 'HOST:5432:appdb:app_rw:CHANGE_ME' > ~/.pgpass && chmod 600 ~/.pgpass
```

Format `host:port:database:user:password`; `*` is a wildcard. libpq ignores
the file if permissions are wider. Never set `PGPASSWORD` inline: it is
visible in the process environment and history. See
[06-security/passwords-and-secrets.md](../06-security/passwords-and-secrets.md).

## Running tools as the postgres OS user

| Command | Purpose | Notes |
|---|---|---|
| `sudo -u postgres psql` | Superuser shell via local socket (peer auth) | Prefer a scoped role for routine work: [06-security/least-privilege.md](../06-security/least-privilege.md) |
| `sudo -u postgres createdb appdb` / `dropdb` | Create / drop a database from the shell | `dropdb` is **destructive**: confirm with `psql -l`, back up first |
| `sudo -u postgres pg_dump -Fc -f /var/backups/appdb.dump appdb` | Backup | Make sure the target directory is writable by `postgres`; flags in [pg-dump.md](pg-dump.md) |
| `psql -h HOST -U USER -d DBNAME` | Remote client | Needs a matching `pg_hba.conf` rule |

## Troubleshooting

| Symptom | Check | Fix |
|---|---|---|
| `psql: ... Connection refused` | `pg_lsclusters` / `systemctl status`; `ss -ltnp \| grep 5432` | Start the cluster; check the port (a second cluster may use 5433) |
| `could not connect to server: No such file or directory` (socket) | Socket directory differs | `psql -h /var/run/postgresql` or use `-h localhost` |
| `Peer authentication failed for user` | Local socket uses peer auth | `sudo -u USER psql`, or connect with `-h 127.0.0.1` and a password |
| Service "active" but clients refused | `listen_addresses`, `pg_hba.conf`, firewall | Edit config, then `systemctl reload` |
| Debian: unit active but `pg_lsclusters` says `down` | Umbrella unit is not the cluster | Start `postgresql@16-main` |

Related: [psql.md](psql.md), [14-observability/](../14-observability/),
[15-production-runbooks/](../15-production-runbooks/).
