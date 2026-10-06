# `psql` Reference

`psql` is the PostgreSQL interactive terminal (a client program, not part
of the server). This page has three command types — keep them apart:

| Type | Where you type it | Example |
|---|---|---|
| **psql command-line flag** | OS shell (bash, zsh, PowerShell, CMD) | `psql -h HOST -d DB -c "SELECT 1"` |
| **psql meta-command** | Inside `psql`, starts with `\` — handled by the client, never sent to the server | `\dt`, `\d+ orders`, `\timing` |
| **SQL** | Inside `psql`, ends with `;` (or `\g`) — sent to the server | `SELECT 1;` — see [sql.md](sql.md) |

`\dt` is not SQL. There is no SQL statement that does what it does; a
driver or another client has no equivalent.

Versions: verified against PostgreSQL 16 (`psql --help`, `\?`, the
[psql 16 docs](https://www.postgresql.org/docs/16/app-psql.html)). Items
marked **PG16+** do not exist in older clients.

## Connecting

```bash
psql -h HOST -p 5432 -U USER -d DBNAME
psql "postgresql://USER@HOST:5432/DBNAME?sslmode=require"
psql "host=HOST port=5432 dbname=DBNAME user=USER sslmode=require"
```

Expected: a `DBNAME=>` prompt (`=#` for a superuser). Confirm where you
landed with `\conninfo`:

```text
You are connected to database "appdb" as user "postgres" on host "127.0.0.1" at port "5616".
```

Do not put the password in the URI or command line — it lands in shell
history and `ps` output. Use `~/.pgpass` or a secrets manager; see
[06-security/passwords-and-secrets.md](../06-security/passwords-and-secrets.md).
For TLS modes see [06-security/ssl.md](../06-security/ssl.md).

### Environment variables (read by psql and every libpq client)

| Variable | Equivalent | Notes |
|---|---|---|
| `PGHOST` | `-h` | |
| `PGPORT` | `-p` | |
| `PGUSER` | `-U` | |
| `PGDATABASE` | `-d` | |
| `PGSSLMODE` | `sslmode=` | `require` encrypts only; `verify-full` also checks the certificate and host name |
| `PGPASSFILE` | path to password file | Default `~/.pgpass` (Unix), `%APPDATA%\postgresql\pgpass.conf` (Windows). On Unix the file must be `chmod 0600` or libpq ignores it |
| `PGPASSWORD` | password | **Avoid** — visible in the process environment; docs discourage it. Never inline it (`PGPASSWORD=x psql`) in a shared shell |
| `PSQLRC` | alternate `~/.psqlrc` path | |
| `PAGER` / `PSQL_PAGER` | pager for long output | |
| `EDITOR` / `PSQL_EDITOR` | editor for `\e` | |

## Command-line flags

| Flag | Purpose | Production notes |
|---|---|---|
| `-h, --host` | Server host or socket directory | Omitted = local Unix socket (macOS/Linux) |
| `-p, --port` | Server port | Default 5432 |
| `-U, --username` | Role to connect as | Use a scoped role, not `postgres` — [06-security/least-privilege.md](../06-security/least-privilege.md) |
| `-d, --dbname` | Database (or a connection string) | |
| `-w, --no-password` | Never prompt for a password; fail instead | Use in scripts/cron so a missing credential fails fast instead of hanging |
| `-W, --password` | Force a password prompt | Rarely needed; libpq prompts automatically when the server asks |
| `-c "CMD"` | Run one command (SQL or meta-command) and exit | Sent as-is: **no `:variable` interpolation** (see below). Multiple `-c` run in order |
| `-f FILE` | Run a script file and exit (`-f -` = stdin) | Pair with `-v ON_ERROR_STOP=1` |
| `-l, --list` | List databases and exit (same as `\l`) | |
| `-X, --no-psqlrc` | Skip `~/.psqlrc` | Use in every script so a local `.psqlrc` cannot change behavior |
| `-v NAME=VALUE` | Set a psql variable | `-v ON_ERROR_STOP=1` is the one to memorize |
| `-1, --single-transaction` | Run the whole `-f`/`-c` set in one transaction | All-or-nothing. Do not combine with statements that cannot run in a transaction (`CREATE INDEX CONCURRENTLY`, `VACUUM`) |
| `-A, --no-align` | Unaligned output | |
| `-t, --tuples-only` | Rows only: no header, no row-count footer | |
| `-F SEP` | Field separator for unaligned output (default `\|`) | |
| `--csv` | CSV output | Quoting is handled; prefer over `-A -F,` for data with commas |
| `-x, --expanded` | One column per line | For wide rows |
| `-q, --quiet` | Suppress informational messages | |
| `-o FILE` | Send query output to a file | |
| `-e` / `-a` / `-b` | Echo queries / echo all input / echo failed commands | `-e` is useful in CI logs |
| `-E, --echo-hidden` | Print the SQL behind `\d`-style commands | Handy to learn the catalog queries |
| `-P VAR=ARG` | Set a `\pset` option, e.g. `-P pager=off` | |
| `-L FILE` | Also log the session to a file | May capture sensitive data — protect the file |
| `-V` / `-?` | Version / help (`--help=commands`, `--help=variables`) | |
| `--no-psqlrc` | Long form of `-X` | |

### Scripting recipes

```bash
# Always: no psqlrc, stop on first error, fail fast on missing password
psql -X -w -v ON_ERROR_STOP=1 -d DBNAME -f migration.sql

# One scalar for use in a shell variable
psql -X -tAc "SELECT count(*) FROM app.orders"            # prints: 3

# CSV export of a query result
psql -X --csv -d DBNAME -c "SELECT id, customer FROM app.orders ORDER BY id"

# Variables: -c does NOT interpolate :name — feed the text through stdin or -f
echo "SELECT count(*) FROM :tbl WHERE total >= :min_total;" \
  | psql -X -d DBNAME -v tbl=app.orders -v min_total=2 -tA
echo "SELECT count(*) FROM app.orders WHERE customer = :'cust';" \
  | psql -X -d DBNAME -v cust=a -tA                       # :'x' quotes as a literal
```

`-c 'SELECT :x' -v x=1` fails with `syntax error at or near ":"`.
Interpolation with `:'name'` is for psql scripts and convenience only; for
untrusted input use parameterized queries from application code (see
[AGENTS.md](../AGENTS.md) section 6) rather than shell-built SQL.

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Fatal psql error, including a failed `-c` command (observed) |
| `2` | Could not connect (non-interactive session) |
| `3` | SQL error in a script and `ON_ERROR_STOP` was set |

Without `ON_ERROR_STOP=1`, `psql -f script.sql` keeps going after a failed
statement and exits `0`, leaving the script half-applied while looking
successful. Always set it for automation. See
[09-alembic/](../09-alembic/) for migration tooling that wraps this.

## Meta-commands (inside psql)

All rows are **psql client commands**, not SQL, not OS commands. Typed
inside a `psql` session; also usable via `psql -c '\dt'`.

### Help and session

| Meta-command | Purpose | Production notes |
|---|---|---|
| `\?` | List meta-commands (`\? variables`, `\? options`) | |
| `\h [STATEMENT]` | Syntax help for a **SQL** statement, e.g. `\h CREATE INDEX` | Reflects the connected psql's version; confirm against the server version |
| `\q` | Quit | |
| `\conninfo` | Current database, user, host, port | First check when "which server am I on?" is unclear |
| `\c [DB [USER [HOST [PORT]]]]` / `\connect` | Reconnect to another database/role | New session: session `SET`s and open transaction are gone |
| `\timing [on\|off]` | Show per-statement time | Client-side wall time including network round trip |
| `\x [on\|off\|auto]` | Expanded display | `\x auto` switches only for wide rows |
| `\! CMD` | Run an OS shell command | |
| `\password [ROLE]` | Change a password with a hidden prompt | Hashes client-side; avoids `ALTER ROLE ... PASSWORD '...'` landing in history/logs |

### Listing and describing objects

| Meta-command | Purpose | Notes |
|---|---|---|
| `\l[+]` | List databases | `+` adds size, tablespace |
| `\dn[+]` | List schemas | |
| `\dt[+] [PATTERN]` | List tables | Honors `search_path`; use `\dt *.*` or `\dt app.*` for other schemas. `+` adds size |
| `\d [NAME]` | Describe a relation (columns, indexes, constraints, FKs); no argument lists all relations | |
| `\d+ NAME` | `\d` plus storage, compression, stats target, description | |
| `\dv[+]` / `\dm[+]` | Views / materialized views | |
| `\di[+]` | Indexes | `+` shows size |
| `\ds[+]` | Sequences | |
| `\df[+] [PATTERN]` | Functions | Pattern it (`\df app.*`); extensions add very wide rows |
| `\sf NAME` | Show a function's definition | |
| `\du[+]` / `\dg` | Roles | Shows attributes, not passwords |
| `\drg` | Role memberships (grants) with `INHERIT`/`SET` options | **PG16+** |
| `\dx[+]` | Installed extensions | |
| `\dp [PATTERN]` (also `\z`) | Table/column privileges (ACLs) | Audit with [06-security/permissions.md](../06-security/permissions.md) |
| `\ddp` | Default privileges (`ALTER DEFAULT PRIVILEGES`) | |

Each accepts a pattern (`\dt app.ord*`). Append `S` (e.g. `\dtS`) to include
system objects.

### Running and shaping queries

| Meta-command | Purpose | Notes |
|---|---|---|
| `\g [FILE]` | Run the query buffer (same as `;`); optionally write output to FILE or `\| cmd` | |
| `\gx` | Run the buffer with expanded output once | |
| `\gset [PREFIX]` | Store a one-row result in psql variables | `SELECT count(*) AS c FROM t \gset` then `:c` |
| `\gexec` | Run each cell of the result as its own SQL statement | Generates and executes SQL. Treat the generating query as a script: review its output first (`\g` without `exec`) before running against production |
| `\watch [SEC]` / `\watch i=SEC c=COUNT` | Re-run the query buffer on an interval | `i=`/`c=` syntax is **PG16+**. Stops with Ctrl-C. Frequent polling of a heavy query adds load |
| `\e [FILE]` | Edit the buffer in `$EDITOR` / `$PSQL_EDITOR` | |
| `\i FILE` | Run SQL from a file (client path) | `\ir` resolves relative to the calling script |
| `\o [FILE]` | Send results to a file; bare `\o` stops | |
| `\set [NAME [VALUE]]` | Set/list psql variables (`\set ON_ERROR_STOP on`) | `\unset NAME` clears |
| `\echo TEXT` | Print text (`\echo :NAME`) | |
| `\pset [OPTION [VALUE]]` | Output options: `format`, `null`, `border`, `pager`, `expanded`, `tuples_only` | `\pset null '(null)'` distinguishes NULL from empty string |
| `\copy ...` | Client-side bulk copy (see below) | |

### `\copy` vs `COPY`

| | `\copy` (psql meta-command) | `COPY` (SQL statement) |
|---|---|---|
| Runs on | The **client**: psql reads/writes the file | The **server** process |
| File path resolved on | The machine running `psql` | The database server host |
| Permission needed | Normal table privileges + client file access | Server file access needs superuser or `pg_read_server_files` / `pg_write_server_files`; the file is accessed as the OS user running PostgreSQL |
| Typical use | Load/export from a laptop, CI runner, or against managed PostgreSQL (no server file access) | Server-local files, `STDIN`/`STDOUT` from a driver |

```text
\copy (SELECT * FROM app.orders ORDER BY id) TO 'orders.csv' CSV HEADER
\copy app.orders (customer, total) FROM 'orders.csv' CSV HEADER
```

Expected: `COPY 3`. Server-side equivalent
`COPY (SELECT ...) TO '/path' WITH (FORMAT csv, HEADER)` fails with
`could not open file ... Permission denied` when the PostgreSQL OS user
cannot write there. Managed services (RDS, Cloud SQL, Azure) do not grant
server file access: use `\copy`.

`\copy` data is streamed through the client connection; for very large
loads, run it from a host close to the server and keep it in a
transaction only if you need all-or-nothing.

## Destructive or risky patterns

| Pattern | What it does | Why risky | Safer alternative / precaution |
|---|---|---|---|
| `psql -f dump.sql` (plain pg_dump output with `--clean`) | Drops and recreates objects | Silent data loss if pointed at the wrong database | Run `\conninfo` first; restore into a new database; see [pg-restore.md](pg-restore.md) |
| `\gexec` over generated `DROP`/`DELETE` | Executes every generated statement | One bad filter in the generator drops everything | Print first (`\g`), review, then `\gexec`; use a role with limited privileges |
| `-f` without `ON_ERROR_STOP=1` | Continues after errors | Half-applied script, exit code `0` | Always `-v ON_ERROR_STOP=1`; add `-1` for all-or-nothing |
| `\c` mid-script | Switches database | Later statements run on the wrong target | `\conninfo` / `SELECT current_database();` as the first line of any script |
| `PGPASSWORD=... psql` | Inline secret | History/process-table exposure | `.pgpass`, `PGPASSFILE`, secrets manager |

## Troubleshooting

| Symptom | Likely cause | Check |
|---|---|---|
| `connection refused` | Server down or wrong host/port | `pg_isready -h HOST -p PORT`; OS pages ([linux.md](linux.md), [macos.md](macos.md), [windows.md](windows.md)) |
| `password authentication failed` | Wrong password or `pg_hba.conf` method | Check `.pgpass` permissions, role, `pg_hba.conf` |
| `no pg_hba.conf entry for host` | Client address/role/db not allowed (or SSL required) | [06-security/ssl.md](../06-security/ssl.md) |
| `psql: command not found` | Client not installed / not on `PATH` | OS page for PATH |
| `syntax error at or near ":"` with `-c` and `-v` | `-c` does not interpolate variables | Use `-f -` / stdin |
| Output scrolls or hangs in a pager | Pager on in a script | `-P pager=off` or `PAGER=cat` |

More background: [01-postgresql-cli/commands.md](../01-postgresql-cli/commands.md),
[01-postgresql-cli/examples/psqlrc.sample](../01-postgresql-cli/examples/psqlrc.sample).
Locks and activity: [14-observability/pg-stat-activity.md](../14-observability/pg-stat-activity.md).

## Quick revision

- Scripts: `psql -X -w -v ON_ERROR_STOP=1 -d DB -f file.sql`.
- `-c` does not expand `:vars`; `-t -A` for one scalar; `--csv` for CSV.
- Exit 3 = script error with `ON_ERROR_STOP`; 2 = could not connect.
- `\copy` is client-side, `COPY` is server-side; managed services only allow `\copy`.
- `\gexec` runs generated SQL; review before executing.
- `\drg` and `\watch i= c=` need psql 16+.
