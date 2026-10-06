# macOS Command Reference

All commands here are **Unix shell** (zsh, the macOS default, or bash)
unless marked `psql` or SQL. Primary install path covered: Homebrew
(`postgresql@16`). Postgres.app and the EDB installer manage the server
differently; see the end of the page.

Validation status: documentation-verified, not executed (no macOS host).
`lsof`, `nc`, `pg_isready`, `pg_ctl`, `psql` syntax was executed on Linux with
the same flags; Homebrew paths and `brew services` come from the Homebrew
documentation. Cross-OS comparison: [README.md](README.md).

## Install and PATH

| Command | Purpose | Notes |
|---|---|---|
| `brew install postgresql@16` | Install the server and client tools | Pick the major version deliberately; versioned formulae are "keg-only" |
| `brew --prefix postgresql@16` | Print the install prefix | `/opt/homebrew/opt/postgresql@16` on Apple silicon, `/usr/local/opt/postgresql@16` on Intel |
| `echo 'export PATH="$(brew --prefix postgresql@16)/bin:$PATH"' >> ~/.zshrc` | Put `psql`, `pg_dump`, `pg_ctl` on `PATH` | Needed because versioned formulae are not linked into `/opt/homebrew/bin` |
| `psql --version` | Confirm client version | Use a client at least as new as the server for `pg_dump` |

## Service control (Homebrew)

| Task | Command | Production Notes |
|---|---|---|
| List services | `brew services list` | Status column: `started`, `stopped`, `error` |
| Status | `brew services info postgresql@16` | Does not prove connections work: `pg_isready` |
| Start | `brew services start postgresql@16` | Registers a launchd agent and starts at login |
| Stop | `brew services stop postgresql@16` | Disconnects clients |
| Restart | `brew services restart postgresql@16` | Drops all connections |
| Reload config | `pg_ctl reload -D "$(brew --prefix)/var/postgresql@16"` | Or SQL `SELECT pg_reload_conf();` |
| Run once, not as a service | `pg_ctl -D "$(brew --prefix)/var/postgresql@16" -l "$(brew --prefix)/var/log/postgresql@16.log" start` | Stop with `pg_ctl ... stop -m fast`. Do not mix with `brew services` on the same data directory |
| Server status via `pg_ctl` | `pg_ctl -D "$(brew --prefix)/var/postgresql@16" status` | |

Homebrew defaults: data directory `$(brew --prefix)/var/postgresql@16`,
log `$(brew --prefix)/var/log/postgresql@16.log`, role named after your macOS
user (no `postgres` superuser unless you create it), trust-style local
authentication. This is a development setup, not a production hardening
baseline ([06-security/](../06-security/)). Production databases do not run
on a laptop.

## Logs

| Command | Purpose | Notes |
|---|---|---|
| `tail -f "$(brew --prefix)/var/log/postgresql@16.log"` | Follow the server log | |
| `grep -iE 'fatal\|error' "$(brew --prefix)/var/log/postgresql@16.log" \| tail -20` | Recent errors | |

## Network checks

| Command | Purpose | Notes |
|---|---|---|
| `lsof -nP -iTCP:5432 -sTCP:LISTEN` | Who listens on 5432 | Shows `postgres ... 127.0.0.1:5432 (LISTEN)` (verified syntax on Linux; same flags on macOS `lsof`) |
| `nc -zv localhost 5432` | TCP reachability | `succeeded!` = port open, not that PostgreSQL authenticates |
| `pg_isready -h localhost -p 5432` | Server accepting connections | Exit 0 = yes |
| `ps aux \| grep '[p]ostgres'` | Server processes | Shows the `-D` data directory |

## Environment variables and passwords

```bash
export PGHOST=localhost PGPORT=5432 PGUSER=app_rw PGDATABASE=appdb
psql -X -c "SELECT current_user, current_database();"
```

Add non-secret variables to `~/.zshrc`. Passwords go in `~/.pgpass` with
`chmod 600 ~/.pgpass` (format `host:port:database:user:password`). Do not
set `PGPASSWORD` inline: it reaches shell history and the process
environment. See
[06-security/passwords-and-secrets.md](../06-security/passwords-and-secrets.md).

## Common tasks

| Command | Purpose | Notes |
|---|---|---|
| `createdb appdb` | Create a database as your macOS user's role | **Shell command**, not SQL |
| `dropdb appdb` | Drop it | **Destructive**: confirm `psql -l` first; take a `pg_dump` |
| `psql -d postgres -c '\l'` | List databases | `\l` is a psql meta-command |
| `pg_dump -Fc -d appdb -f ~/backups/appdb.dump` | Backup | Flags in [pg-dump.md](pg-dump.md) |

## Other installs

| Install | Binaries | Service |
|---|---|---|
| Postgres.app | `/Applications/Postgres.app/Contents/Versions/latest/bin` (add to `PATH`) | Start/stop in the app; no `brew services` |
| EDB installer | `/Library/PostgreSQL/16/bin` | launchd; `pg_ctl` against `/Library/PostgreSQL/16/data` |
| Docker Desktop | n/a on host | Use [docker.md](docker.md); the host port mapping is `-p 5432:5432` |

## Troubleshooting

| Symptom | Check | Fix |
|---|---|---|
| `psql: command not found` | `PATH` | Add `$(brew --prefix postgresql@16)/bin` |
| `connection refused` | `brew services list`; log file | `brew services start postgresql@16`; read the log |
| `FATAL: role "postgres" does not exist` | Homebrew creates a role for your macOS user | `psql -d postgres` as yourself, or `createuser -s postgres` for dev only |
| Service shows `error` after a crash or force quit | Server log; leftover `postmaster.pid` in the data directory | Confirm no postgres process (`ps`), read the log, then `brew services restart postgresql@16` |
| Port already in use | `lsof -nP -iTCP:5432 -sTCP:LISTEN` | Another instance (Postgres.app or Docker) holds 5432; change `port` or stop it |

Related: [psql.md](psql.md), [01-postgresql-cli/commands.md](../01-postgresql-cli/commands.md).
