# PostgreSQL CLI Commands

## What it is

The command surface for working with a PostgreSQL server from a terminal:
connecting with `psql`, the `psql` meta-commands used once connected, and
the OS-level commands that start, stop, and check the server process
itself.

## Why it matters

Before you can run a query, design a schema, or debug a slow transaction,
you need to reliably connect to the right server and know whether it's
even running. Most "the database is down" incidents start with one of
these commands.

## Connecting with `psql`

```
psql -h HOST -p PORT -U USER -d DBNAME
```

| Flag | Meaning |
|---|---|
| `-h` | Host (defaults to a local Unix socket on macOS/Linux if omitted, `localhost` on Windows) |
| `-p` | Port (default `5432`) |
| `-U` | Role/username to connect as |
| `-d` | Database name |
| `-W` | Force a password prompt instead of relying on `.pgpass`/trust auth |

`psql` also accepts a single connection URI, which is convenient for
scripts and matches the `DATABASE_URL` format used elsewhere in this repo
(see [08-python-fastapi/](../08-python-fastapi/)):

```
psql "postgresql://USER:PASSWORD@HOST:PORT/DBNAME"
```

### Connection environment variables

`psql` (and every other libpq-based client, including `pg_dump`) reads
these if the matching flag isn't given:

| Variable | Same as flag |
|---|---|
| `PGHOST` | `-h` |
| `PGPORT` | `-p` |
| `PGUSER` | `-U` |
| `PGDATABASE` | `-d` |
| `PGPASSWORD` | password (see warning below) |
| `PGPASSFILE` | path to a `.pgpass`-format file (default `~/.pgpass`) |

**Production note:** don't set `PGPASSWORD` inline
(`PGPASSWORD=secret psql ...`) — it can end up in shell history and is
visible to other processes on the same host via `ps`. Use a `.pgpass` file
(`chmod 600 ~/.pgpass`) or a secrets manager instead. See
[06-security/passwords-and-secrets.md](../06-security/passwords-and-secrets.md).

## psql meta-commands

Anything typed in `psql` that starts with an unquoted backslash is a
**psql meta-command** — it's handled by the `psql` client itself, not sent
to the server as SQL. `\dt` is not SQL; there is no SQL statement that does
what `\dt` does.

| Meta-command | Purpose | Production notes |
|---|---|---|
| `\l` | List databases | Read-only, safe anywhere |
| `\c dbname [user] [host] [port]` (or `\connect`) | Switch connection to another database/role | Drops and re-establishes the session; in-progress transaction state is lost |
| `\dt` | List tables in the current schema search path | Add `+` (`\dt+`) for size and description |
| `\d name` | Describe a table/view/sequence/index (columns, types, indexes, constraints) | With no argument, lists tables/views/sequences like a combined `\dt` |
| `\d+ name` | Same as `\d`, plus storage/size details | Use before altering a table you don't know well |
| `\dn` | List schemas | |
| `\du` | List roles and their attributes (superuser, login, etc.) | Does not show role passwords |
| `\dx` | List installed extensions (e.g. `pgvector`, `pg_stat_statements`) | |
| `\conninfo` | Show current host, port, database, user, and SSL status | First thing to check when "which database am I on?" is unclear |
| `\timing` | Toggle display of each statement's execution time | Leave on during any production investigation |
| `\x` | Toggle expanded (one-column-per-line) output | Essential for wide rows — put it in `.psqlrc` |
| `\q` | Quit `psql` | |
| `\?` | Help on `psql` meta-commands | |
| `\h STATEMENT` | Help on SQL syntax, e.g. `\h CREATE INDEX` | |
| `\i file.sql` | Execute SQL from a file | |
| `\o file` | Redirect query output to a file | Remember to run `\o` with no argument to stop redirecting |
| `\e` | Open the current query buffer in `$EDITOR` | |
| `\password [role]` | Change a role's password via a prompt (never echoed) | Prefer this over `ALTER ROLE ... PASSWORD '...'` typed directly, which lands in `.psql_history` |
| `\copy` | Client-side bulk import/export, run as the connecting role | Safer than server-side `COPY` when the file must live on the client, not the server |

## Service management

These start/stop/restart the PostgreSQL **server process**, not a client
session. Exact service/unit names vary by how PostgreSQL was installed —
confirm the name before assuming it.

| Task | Windows (PowerShell) | macOS (Homebrew) | Linux (systemd) | Production notes |
|---|---|---|---|---|
| Find the service/unit name | `Get-Service postgresql*` | `brew services list` | `systemctl list-units 'postgresql*'` | Names are version-suffixed (`postgresql-x64-16`, `postgresql@16`, `postgresql@16-main`) — don't hardcode a version |
| Check status | `Get-Service postgresql-x64-<ver>` | `brew services info postgresql@<ver>` | `systemctl status postgresql` | Does not confirm the server accepts connections — use `pg_isready` for that |
| Start | `Start-Service postgresql-x64-<ver>` | `brew services start postgresql@<ver>` | `sudo systemctl start postgresql` | |
| Stop | `Stop-Service postgresql-x64-<ver>` | `brew services stop postgresql@<ver>` | `sudo systemctl stop postgresql` | Terminates all active sessions abruptly; drain traffic first where possible |
| Restart | `Restart-Service postgresql-x64-<ver>` | `brew services restart postgresql@<ver>` | `sudo systemctl restart postgresql` | Drops every open connection — plan a maintenance window; app connection pools must reconnect |
| Enable at boot | (set via Services MMC or `Set-Service -StartupType Automatic`) | `brew services start` enables by default | `sudo systemctl enable postgresql` | |
| Tail server logs | Event Viewer, or the configured `log_directory` | `tail -f $(brew --prefix)/var/log/postgresql@<ver>.log` | `journalctl -u postgresql -f` | Check logs before restarting — the cause of an outage is usually already there |

**Cross-platform alternative — `pg_ctl`:** when PostgreSQL is not registered
as an OS service (common in local development, or containers), manage a
specific data directory directly:

```
pg_ctl -D /path/to/data start
pg_ctl -D /path/to/data stop -m fast
pg_ctl -D /path/to/data restart
pg_ctl -D /path/to/data status
```

`-m fast` (stop) rolls back in-progress transactions and disconnects
clients immediately — faster than the default `-m smart`, which waits for
clients to disconnect on their own. Never use `-m immediate` on a
production instance except as a last resort: it skips a clean shutdown
checkpoint and forces crash recovery on the next start.

## Checking connectivity

```
pg_isready -h HOST -p PORT
```

`pg_isready` is a lightweight libpq client that just checks whether the
server is accepting connections — it does not require valid login
credentials. It's the right tool for health checks (see
[12-docker/](../12-docker/) healthchecks and
[scripts/health-check/](../scripts/health-check/)).

| Exit code | Meaning |
|---|---|
| `0` | Server is accepting connections |
| `1` | Server is rejecting connections (e.g. still starting up) |
| `2` | No response to the connection attempt (host/port unreachable) |
| `3` | No attempt made — invalid parameters given to `pg_isready` itself |

For raw network-level reachability (before you even know if PostgreSQL is
listening), OS tools like PowerShell's `Test-NetConnection` or Unix `nc`
are covered in [16-command-reference/](../16-command-reference/) rather
than duplicated here.

## Common mistakes

- Passing `PGPASSWORD=...` inline on the command line — leaks via shell
  history and `ps`. Use `.pgpass` or a secrets manager.
- Connecting as the `postgres` superuser for routine application or
  debugging work. Use a scoped role — see
  [06-security/least-privilege.md](../06-security/least-privilege.md).
- Assuming the service/unit name (`postgresql`, `postgresql-14`,
  `postgresql@16`) without checking — it depends on the OS, package
  manager, and installed version.
- Treating `\d`/`\dt` as SQL. They are `psql`-only meta-commands; a
  different client (a driver, another CLI) has no equivalent syntax.
- Running `pg_ctl ... stop -m immediate` on a production instance instead
  of `-m fast` or a graceful drain.

## Security considerations

- `.pgpass` must be `chmod 600` (or the equivalent ACL on Windows) — libpq
  refuses to use it otherwise on Unix-like systems.
- Prefer `\password` over typing `ALTER ROLE ... PASSWORD '...'` — the
  latter is recorded in `.psql_history` in plaintext.
- Separate roles for interactive/admin access vs. application connections;
  see [06-security/roles.md](../06-security/roles.md).

## Production considerations

- Stopping/restarting the service disconnects every client immediately
  (or after they finish, with `-m smart`/`systemctl stop`'s default
  behavior) — coordinate with application connection pools, which need to
  detect the drop and reconnect.
- `pg_isready` returning `0` means the server accepts connections; it does
  **not** mean queries are fast or replication is caught up. Pair it with
  the checks in [14-observability/](../14-observability/).
- For "is Postgres actually down" incidents, start at
  [15-production-runbooks/database-is-down.md](../15-production-runbooks/database-is-down.md).

## AI/agentic use case

Agent orchestration systems that depend on PostgreSQL-backed state (see
[11-agentic-ai/](../11-agentic-ai/)) should call `pg_isready` as a
pre-flight check before starting a workflow step that will read or write
that state, rather than letting the first query fail deep inside agent
logic. The scripts in
[scripts/health-check/](../scripts/health-check/) build on this.

## Troubleshooting

| Symptom | Likely cause | Check |
|---|---|---|
| `psql: error: connection to server ... failed: Connection refused` | Server not running, wrong host/port | `pg_isready -h HOST -p PORT`; service status |
| `psql: error: ... FATAL: password authentication failed for user` | Wrong credentials, or `pg_hba.conf` auth method mismatch | Confirm password; check `pg_hba.conf` |
| `psql: command not found` | `psql` not installed or not on `PATH` | Confirm install location; add to `PATH` |
| `psql: error: connection to server ... failed: FATAL: no pg_hba.conf entry` | Client host/user/database not permitted | Review `pg_hba.conf` rules |

## Quick revision

- Connect: `psql -h HOST -p PORT -U USER -d DBNAME`, or set `PGHOST`/`PGPORT`/`PGUSER`/`PGDATABASE`.
- Never put a password inline — use `.pgpass`.
- `\l`, `\c`, `\dt`, `\d`, `\dn`, `\du`, `\dx`, `\conninfo`, `\timing`, `\x`, `\q` are psql meta-commands, not SQL.
- Service control differs by OS: `Start-Service`/`Stop-Service` (Windows), `brew services` (macOS), `systemctl` (Linux); `pg_ctl` works everywhere against a data directory.
- `pg_isready` tells you if the server accepts connections — check it before assuming an outage.
