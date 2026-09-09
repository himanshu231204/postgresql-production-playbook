# macOS Command Reference

Commands below assume a Homebrew install (`brew install postgresql@16`),
the common case for local development on macOS. For the *why* behind
service management and connecting, see
[01-postgresql-cli/commands.md](../01-postgresql-cli/commands.md) — this
page is the fast lookup, organized by OS instead of by topic.

## Service management

| Task | Command | Notes |
|---|---|---|
| List installed/managed services | `brew services list` | Shows every Homebrew-managed background service, not just PostgreSQL |
| Check status | `brew services info postgresql@<ver>` | Does not confirm the server accepts connections — use `pg_isready` |
| Start | `brew services start postgresql@<ver>` | Registers with `launchd` so it also starts at login |
| Stop | `brew services stop postgresql@<ver>` | Drops every open connection |
| Restart | `brew services restart postgresql@<ver>` | |
| Run in the foreground (no `launchd` registration) | `postgres -D /opt/homebrew/var/postgresql@<ver>` | Useful for seeing startup errors directly in the terminal |

## Environment variables

| Task | Command | Notes |
|---|---|---|
| Set for the current session only | `export PGHOST=localhost` | Lost when the terminal closes |
| Set persistently | Add the `export` line to `~/.zshrc` (zsh, the default shell since macOS Catalina) or `~/.bash_profile` (bash) | Takes effect in **new** shells, or run `source ~/.zshrc` |
| Read a variable | `echo $PGHOST` | |

**Production note:** don't `export PGPASSWORD` in a shell profile — it's
readable by anything running as that user and shows up in `ps` for any
subprocess that inherits it. Use `~/.pgpass` (`chmod 600`) or a secrets
manager; see
[06-security/passwords-and-secrets.md](../06-security/passwords-and-secrets.md).

## Network diagnostics

```bash
nc -zv HOST 5432
```

`-z` scans without sending data, `-v` prints whether the connection
succeeded. This only confirms the TCP port is reachable — it doesn't mean
PostgreSQL itself is healthy. Compare against `pg_isready`, which checks
the PostgreSQL process specifically (see
[01-postgresql-cli/commands.md](../01-postgresql-cli/commands.md#checking-connectivity)).

## Running `psql`, `pg_dump`, `pg_restore`

Homebrew's versioned PostgreSQL formulas are not linked onto `PATH` by
default (to avoid colliding with other versions). Either run
`brew link postgresql@<ver>` or reference the binaries directly:

```bash
$(brew --prefix postgresql@16)/bin/psql -h localhost -U app_user -d app_db
```

See [psql.md](psql.md), [pg-dump.md](pg-dump.md), and
[pg-restore.md](pg-restore.md) for the flags themselves.

## Docker

Docker Desktop for Mac is required (there's no native Linux container
runtime on macOS). Once running, `docker`/`docker compose` commands are
identical to Linux — see [docker.md](docker.md). The official
`postgres` image publishes both `amd64` and `arm64` builds, so Apple
Silicon doesn't need an emulated platform for it.

## Common mistakes

- Assuming `psql` is on `PATH` right after `brew install` — versioned
  formulas usually aren't linked automatically.
- Forgetting the version suffix in `brew services` commands
  (`postgresql@16`, not `postgresql`) when multiple versions are
  installed.
