# PostgreSQL CLI Examples

Small, runnable examples supporting [../commands.md](../commands.md). None
of these require credentials to be written down anywhere — they read
connection info only from the standard `PG*` environment variables that
`psql`/`pg_isready` already understand.

## `connection-check.sh` (macOS/Linux)

Wraps `pg_isready` and `psql \conninfo` into a single pre-flight check.

```bash
export PGHOST=localhost
export PGPORT=5432
export PGUSER=app_user
export PGDATABASE=app_db
./connection-check.sh
```

Expected output on success:

```
Checking whether the PostgreSQL server is accepting connections...
localhost:5432 - accepting connections
Server is accepting connections. Fetching connection info...
You are connected to database "app_db" as user "app_user" on host "localhost" at port "5432".
```

If the server isn't reachable, `pg_isready` exits non-zero (see the exit
code table in [../commands.md](../commands.md#checking-connectivity)), the
script prints an error to stderr, and exits `1` — safe to use as a
pre-flight check in CI or a deploy script.

Requires: `pg_isready` and `psql` on `PATH`.

## `connection-check.ps1` (Windows)

Same check, in PowerShell:

```powershell
$env:PGHOST = "localhost"
$env:PGPORT = "5432"
$env:PGUSER = "app_user"
$env:PGDATABASE = "app_db"
.\connection-check.ps1
```

Requires: `pg_isready.exe` and `psql.exe` on `PATH` (installed with
PostgreSQL's Windows installer).

## `psqlrc.sample`

An annotated example `~/.psqlrc`, with a comment on why each line is
useful in production work (timing display, explicit `NULL` rendering,
auto-expanded output for wide rows, a host/db-aware prompt, and per-database
history files). Not loaded automatically — copy the lines you want into
your own `~/.psqlrc`.

## Validation performed

- `bash -n connection-check.sh` — syntax-checked, no execution against a
  live server was possible in this environment.
- `connection-check.ps1` was reviewed for syntax but not executed — no
  PowerShell interpreter is available in this environment.
- `psqlrc.sample`'s `HISTFILE` substitution syntax was verified against the
  documented `psql` variable-substitution behavior for `:DBNAME`.
