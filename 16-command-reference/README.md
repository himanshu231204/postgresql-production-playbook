# Command Reference

Lookup tables for the exact command, cut two ways: **by operating system**
and **by tool**. Opened mid-task: Find, Copy, Adapt, Validate. Narrative,
tradeoffs and incident handling live in the numbered sections; these pages
link out instead of repeating them.

Versions: PostgreSQL 16 syntax unless a row says otherwise. Hostnames,
users, passwords and paths are placeholders (`HOST`, `USER`, `DBNAME`).

## Pages

| Page | Command type | Covers | For depth, see |
|---|---|---|---|
| [psql.md](psql.md) | psql flags (OS shell) and psql meta-commands (inside psql) | Connection, scripting flags, exit codes, every common `\` command, `\copy` vs `COPY` | [01-postgresql-cli/commands.md](../01-postgresql-cli/commands.md) |
| [sql.md](sql.md) | PostgreSQL SQL | DDL, DML, indexes, transactions, maintenance, diagnostics; destructive statements flagged | [02-sql-fundamentals/](../02-sql-fundamentals/), [03-database-design/](../03-database-design/), [04-transactions/](../04-transactions/) |
| [pg-dump.md](pg-dump.md) | OS-shell client program | `pg_dump` flags and formats, `pg_dumpall`, `pg_basebackup` | [07-backups-recovery/pg-dump.md](../07-backups-recovery/pg-dump.md) |
| [pg-restore.md](pg-restore.md) | OS-shell client program | `pg_restore` flags, destructive options | [07-backups-recovery/pg-restore.md](../07-backups-recovery/pg-restore.md) |
| [linux.md](linux.md) | Unix shell | `systemctl`, `journalctl`, `pg_lsclusters`, `ss`, env vars; Debian vs RHEL | [15-production-runbooks/database-is-down.md](../15-production-runbooks/database-is-down.md) |
| [macos.md](macos.md) | Unix shell | Homebrew `brew services`, `lsof`, `nc`, env vars | |
| [windows.md](windows.md) | PowerShell and Windows CMD (labeled per row) | `Get-Service`, `Test-NetConnection`, `netstat`, env vars, `pg_ctl.exe` | |
| [docker.md](docker.md) | Docker commands | `docker exec`, `docker compose`, logs, volumes | [12-docker/](../12-docker/) |

## Command types: never mix them

| Type | Looks like | Runs in | Not to be confused with |
|---|---|---|---|
| PostgreSQL SQL | `SELECT 1;` `CREATE TABLE ...;` | Sent to the server by any client | psql meta-commands |
| psql meta-command | `\dt` `\d+` `\l` `\c` `\copy` `\timing` `\x` `\q` | Handled by the `psql` client only | SQL (`\dt` is not SQL) |
| PostgreSQL client program | `psql`, `pg_dump`, `pg_restore`, `pg_isready`, `createdb` | OS shell | SQL or meta-commands |
| Unix shell | `systemctl`, `brew services`, `journalctl`, `ss`, `ps` | bash/zsh (macOS, Linux) | PowerShell |
| PowerShell | `Get-Service`, `Start-Service`, `Test-NetConnection` | Windows PowerShell / PowerShell 7 | CMD |
| Windows CMD | `set`, `setx`, `net start`, `netstat -ano \| findstr` | `cmd.exe` | PowerShell (`$env:X`, pipelines differ) |
| Docker | `docker run`, `docker exec`, `docker compose` | Host shell; runs commands inside containers | Commands run *inside* the container |

## Same task, per operating system

Service names vary by install method and version; confirm yours first. Linux
column shows Debian/Ubuntu first, RHEL-family in [linux.md](linux.md).

| Task | Windows (PowerShell unless noted) | macOS (Homebrew) | Linux (systemd) | Production Notes |
|---|---|---|---|---|
| Find the service | `Get-Service postgresql*` | `brew services list` | `systemctl list-units 'postgresql*'`; Debian: `pg_lsclusters` | Typical names: `postgresql-x64-16`, `postgresql@16`, `postgresql@16-main` / `postgresql-16` |
| Status | `Get-Service postgresql-x64-16` | `brew services info postgresql@16` | `systemctl status postgresql@16-main` | "running" does not mean "accepting connections": use `pg_isready` |
| Start | `Start-Service postgresql-x64-16` | `brew services start postgresql@16` | `sudo systemctl start postgresql@16-main` | |
| Stop | `Stop-Service postgresql-x64-16` | `brew services stop postgresql@16` | `sudo systemctl stop postgresql@16-main` | Disconnects clients; drain traffic first |
| Restart | `Restart-Service postgresql-x64-16` | `brew services restart postgresql@16` | `sudo systemctl restart postgresql@16-main` | Drops every connection; use only for settings that need a restart |
| Reload config (no restart) | `& "C:\Program Files\PostgreSQL\16\bin\pg_ctl.exe" reload -D "C:\Program Files\PostgreSQL\16\data"` | `pg_ctl reload -D "$(brew --prefix)/var/postgresql@16"` | `sudo systemctl reload postgresql@16-main` | Or SQL `SELECT pg_reload_conf();`. On Debian the umbrella unit `postgresql` reload is a no-op |
| Server log | `Get-Content <log_directory>\*.log -Tail 50 -Wait` | `tail -f "$(brew --prefix)/var/log/postgresql@16.log"` | `journalctl -u postgresql@16-main -f` | Read logs before restarting |
| Who listens on 5432 | `netstat -ano \| findstr 5432` (CMD or PowerShell) | `lsof -nP -iTCP:5432 -sTCP:LISTEN` | `ss -ltnp \| grep 5432` | `-p` process names need sudo on Linux |
| TCP reachability | `Test-NetConnection -ComputerName HOST -Port 5432` | `nc -zv HOST 5432` | `nc -zv HOST 5432` | Proves the port is open, not that PostgreSQL answers |
| Server accepting connections | `pg_isready -h HOST -p 5432` | `pg_isready -h HOST -p 5432` | `pg_isready -h HOST -p 5432` | Exit codes 0/1/2/3 in [01-postgresql-cli/commands.md](../01-postgresql-cli/commands.md) |
| Set env var (session) | PowerShell: `$env:PGHOST = "HOST"`; CMD: `set PGHOST=HOST` | `export PGHOST=HOST` | `export PGHOST=HOST` | Never put `PGPASSWORD` in history; see [06-security/passwords-and-secrets.md](../06-security/passwords-and-secrets.md) |
| Password file | `%APPDATA%\postgresql\pgpass.conf` | `~/.pgpass` (`chmod 600`) | `~/.pgpass` (`chmod 600`) | `PGPASSFILE` overrides the path |
| psql inside a container | `docker exec -it CONTAINER psql -U USER -d DBNAME` | same | same | See [docker.md](docker.md) |

## Validation status

Commands in `psql.md`, `sql.md`, `pg-dump.md` and `pg-restore.md` were
executed against a local PostgreSQL 16 server. Linux `pg_lsclusters`,
`pg_ctl`, `lsof` and `nc` were executed; `systemctl`, `journalctl`, `ss`,
all macOS, Windows and Docker-daemon commands were checked against
documentation and `--help` output only. Each OS page states its own status.

## Related

[CHEATSHEET.md](../CHEATSHEET.md), [QUICKSTART.md](../QUICKSTART.md),
[01-postgresql-cli/](../01-postgresql-cli/),
[14-observability/](../14-observability/),
[15-production-runbooks/](../15-production-runbooks/).
