# Command Reference

## What it is

A fast-lookup command reference, cut two ways instead of one:

- **By OS** — [windows.md](windows.md), [macos.md](macos.md), [linux.md](linux.md):
  everything you'd run on that operating system for PostgreSQL work
  (finding/starting the service, setting environment variables, checking
  network reachability, invoking the backup/restore and Docker tools).
- **By tool** — [psql.md](psql.md), [sql.md](sql.md), [pg-dump.md](pg-dump.md),
  [pg-restore.md](pg-restore.md), [docker.md](docker.md): every flag/command
  for that one tool, independent of OS.

## Why it matters

The numbered sections (`01-postgresql-cli/`, `02-sql-fundamentals/`,
`07-backups-recovery/`, `09-alembic/`, `12-docker/`, ...) explain **why** —
production tradeoffs, security, troubleshooting. This section is the
opposite cut: **what's the exact command**, with no narrative, for when you
already know what you're doing and just need the syntax. Where a topic is
covered in depth elsewhere, these pages link out rather than repeat the
explanation.

## Relationship to `CHEATSHEET.md`

`CHEATSHEET.md` is the single-page, whole-repo version of this idea.
This section is the same style of reference, organized specifically by OS
and by tool, with a bit more room per command.

## Pages

| Page | Covers | Does not cover (see instead) |
|---|---|---|
| [windows.md](windows.md) | PowerShell service control, env vars, `Test-NetConnection`, Docker Desktop notes | psql meta-commands ([01-postgresql-cli/](../01-postgresql-cli/)) |
| [macos.md](macos.md) | Homebrew service control, env vars, `nc`, Docker Desktop notes | psql meta-commands ([01-postgresql-cli/](../01-postgresql-cli/)) |
| [linux.md](linux.md) | `systemctl`, env vars, `ss`/`nc`, native Docker notes | psql meta-commands ([01-postgresql-cli/](../01-postgresql-cli/)) |
| [psql.md](psql.md) | `psql` command-line flags for scripting/automation (`-c`, `-f`, `-A`, `-t`, `-v`, exit codes) | Interactive meta-commands like `\dt`/`\d` ([01-postgresql-cli/commands.md](../01-postgresql-cli/commands.md)) |
| [sql.md](sql.md) | Flat quick-reference table of core SQL statements | Full explanations, tradeoffs, examples ([02-sql-fundamentals/](../02-sql-fundamentals/), [03-database-design/](../03-database-design/), [04-transactions/](../04-transactions/)) |
| [pg-dump.md](pg-dump.md) | `pg_dump` flags and format types | Backup strategy, scheduling, retention ([07-backups-recovery/](../07-backups-recovery/)) |
| [pg-restore.md](pg-restore.md) | `pg_restore` flags | Disaster-recovery process ([07-backups-recovery/](../07-backups-recovery/)) |
| [docker.md](docker.md) | `docker`/`docker compose` commands for running PostgreSQL | Dockerfile/compose design, volumes, healthchecks ([12-docker/](../12-docker/)) |
