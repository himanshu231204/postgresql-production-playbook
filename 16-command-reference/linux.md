# Linux Command Reference

Commands below assume a systemd-based distro (Ubuntu, Debian, RHEL/Rocky,
Fedora — the large majority of production Linux servers). For the *why*
behind service management and connecting, see
[01-postgresql-cli/commands.md](../01-postgresql-cli/commands.md) — this
page is the fast lookup, organized by OS instead of by topic.

## Service management

| Task | Command | Notes |
|---|---|---|
| Find the unit name | `systemctl list-units 'postgresql*'` | Distro-bundled packages often use plain `postgresql`; the official PGDG apt/yum repos use a versioned unit like `postgresql@16-main` |
| Check status | `systemctl status postgresql` | Does not confirm the server accepts connections — use `pg_isready` |
| Start | `sudo systemctl start postgresql` | |
| Stop | `sudo systemctl stop postgresql` | Drops every open connection |
| Restart | `sudo systemctl restart postgresql` | |
| Enable at boot | `sudo systemctl enable postgresql` | |
| Tail logs | `journalctl -u postgresql -f` | Check here before restarting — the cause of an outage is usually already logged |
| Find the running process | `ps aux \| grep postgres` | Shows one process per backend connection plus the postmaster |

## Environment variables

| Task | Command | Notes |
|---|---|---|
| Set for the current session only | `export PGHOST=localhost` | Lost when the shell exits |
| Set persistently for one user | Add the `export` line to `~/.bashrc` or `~/.profile` | Takes effect in new shells, or run `source ~/.bashrc` |
| Set system-wide | Add `PGHOST=localhost` (no `export`) to `/etc/environment` | Applies to all users; requires root; takes effect on next login |
| Read a variable | `echo $PGHOST` | |

**Production note:** don't put `PGPASSWORD` in `/etc/environment` or a
shared profile — every process on the system running as that user (or, for
`/etc/environment`, every user) can read it. Use `~/.pgpass` (`chmod 600`)
or a secrets manager; see
[06-security/passwords-and-secrets.md](../06-security/passwords-and-secrets.md).

## Network diagnostics

```bash
ss -tlnp | grep 5432   # is anything listening locally on 5432?
nc -zv HOST 5432       # can I reach HOST:5432 from here?
```

`ss -tlnp` needs to run on the database host itself; `nc -zv` runs from
the client trying to reach it. Neither confirms PostgreSQL is healthy,
only that the port is listening/reachable — pair with `pg_isready` (see
[01-postgresql-cli/commands.md](../01-postgresql-cli/commands.md#checking-connectivity)).

## Running `psql`, `pg_dump`, `pg_restore`

Distro packages (`apt install postgresql-client`, `dnf install
postgresql`) generally put these on `PATH` already. If multiple major
versions are installed side by side (common with the PGDG repos), use the
versioned binary explicitly, e.g. `/usr/lib/postgresql/16/bin/psql`, or
`update-alternatives` on Debian/Ubuntu to pick a default.

See [psql.md](psql.md), [pg-dump.md](pg-dump.md), and
[pg-restore.md](pg-restore.md) for the flags themselves.

## Docker

Linux runs the Docker Engine natively — no Docker Desktop layer. Standard
`docker`/`docker compose` commands apply directly; see [docker.md](docker.md).
Remember to add your user to the `docker` group (`sudo usermod -aG docker
$USER`, then re-login) if you don't want to prefix every command with
`sudo`.

## Common mistakes

- Assuming the unit name is always `postgresql` — check with
  `systemctl list-units 'postgresql*'` first, especially when the PGDG
  repo is in use.
- Opening PostgreSQL's port in the OS firewall (`ufw`/`firewalld`) without
  also restricting it in `pg_hba.conf` — the firewall and `pg_hba.conf`
  are independent layers; both need to be correct.
- Editing `/etc/environment` and expecting the change to apply to
  already-running processes or sessions.
