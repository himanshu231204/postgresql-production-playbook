# Windows Command Reference

Every row is labeled **PowerShell** or **CMD** (`cmd.exe`). They are
different shells: `$env:PGHOST` is PowerShell only, `set PGHOST=...` is
CMD only, `findstr` and `netstat` run in both. Rows labeled **psql** or
**SQL** run inside a `psql` session. Default install used below: the EDB
installer, service `postgresql-x64-16`, binaries in
`C:\Program Files\PostgreSQL\16\bin`, data in
`C:\Program Files\PostgreSQL\16\data`. Adjust the version and paths to your
install (check with `Get-Service postgresql*`).

Validation status: documentation-verified, not executed (no Windows host).
The `psql`, `pg_isready`, `pg_dump` and `pg_ctl` flags used here were
executed on Linux; PowerShell/CMD cmdlets and switches were checked against
Microsoft documentation. Cross-OS comparison: [README.md](README.md).

## Service control

| Shell | Command | Purpose | Production Notes |
|---|---|---|---|
| PowerShell | `Get-Service postgresql*` | Find the service | Names include the major version, e.g. `postgresql-x64-16` |
| PowerShell | `Get-Service -Name postgresql-x64-16` | Status | `Running` does not mean accepting connections: use `pg_isready` |
| PowerShell | `Start-Service postgresql-x64-16` | Start | Run elevated (Administrator) |
| PowerShell | `Stop-Service postgresql-x64-16` | Stop | Disconnects clients; drain traffic first |
| PowerShell | `Restart-Service postgresql-x64-16` | Restart | Drops all connections |
| PowerShell | `Set-Service -Name postgresql-x64-16 -StartupType Automatic` | Start at boot | |
| CMD | `sc query postgresql-x64-16` | Status | `STATE: 4 RUNNING` |
| CMD | `net start postgresql-x64-16` / `net stop postgresql-x64-16` | Start / stop | Elevated prompt |
| PowerShell | `& "C:\Program Files\PostgreSQL\16\bin\pg_ctl.exe" -D "C:\Program Files\PostgreSQL\16\data" status` | Check via `pg_ctl` | The `&` call operator is required for a quoted path in PowerShell |
| PowerShell | `& "C:\Program Files\PostgreSQL\16\bin\pg_ctl.exe" -D "C:\Program Files\PostgreSQL\16\data" reload` | Reload config without restart | Or SQL `SELECT pg_reload_conf();` |
| PowerShell | `& "...\pg_ctl.exe" -D "...\data" restart -m fast` | Restart a non-service instance | Do not use against a data directory the Windows service already manages. Avoid `-m immediate` (forces crash recovery) |
| CMD | `"C:\Program Files\PostgreSQL\16\bin\pg_ctl.exe" -D "C:\Program Files\PostgreSQL\16\data" status` | Same, CMD quoting | |

## Logs

| Shell | Command | Purpose | Notes |
|---|---|---|---|
| PowerShell | `Get-ChildItem "C:\Program Files\PostgreSQL\16\data\log" \| Sort-Object LastWriteTime -Descending \| Select-Object -First 1 \| Get-Content -Tail 50 -Wait` | Follow the newest log | Path depends on `log_directory`/`logging_collector`; confirm with SQL `SHOW log_directory;` |
| GUI | Event Viewer, Windows Logs, Application | Service start/stop failures | Check before restarting |

## Network checks

| Shell | Command | Purpose | Expected / notes |
|---|---|---|---|
| PowerShell | `Test-NetConnection -ComputerName localhost -Port 5432` | TCP reachability | `TcpTestSucceeded : True` means the port is open, not that PostgreSQL authenticates you |
| PowerShell | `Get-NetTCPConnection -LocalPort 5432 -State Listen` | Who is listening | Shows `OwningProcess` (PID) |
| CMD or PowerShell | `netstat -ano \| findstr 5432` | Listening sockets and PIDs | Last column is the PID; `LISTENING` rows are the server |
| CMD or PowerShell | `tasklist /FI "PID eq 1234"` | Map a PID to a process | Replace `1234` |
| CMD or PowerShell | `pg_isready -h localhost -p 5432` | Server accepting connections | Exit 0 = accepting. PowerShell: `$LASTEXITCODE`; CMD: `echo %ERRORLEVEL%` |

Windows Firewall: allow inbound TCP 5432 only from application subnets.

## Environment variables and passwords

| Shell | Command | Scope |
|---|---|---|
| PowerShell | `$env:PGHOST = "HOST"; $env:PGUSER = "app_rw"; $env:PGDATABASE = "appdb"` | Current session |
| PowerShell | `[Environment]::SetEnvironmentVariable("PGHOST", "HOST", "User")` | Persistent for your user (new shells) |
| PowerShell | `$env:Path += ";C:\Program Files\PostgreSQL\16\bin"` | Add `psql` to `PATH` for this session |
| CMD | `set PGHOST=HOST` | Current window |
| CMD | `setx PGHOST HOST` | Persistent (new windows only) |
| CMD or PowerShell | `where.exe psql` | Is `psql` on `PATH`? (use `where.exe`; `where` alone is a different alias in PowerShell) |

Passwords belong in `%APPDATA%\postgresql\pgpass.conf` (same line format as
Unix `.pgpass`: `host:port:database:user:password`), or `PGPASSFILE` to
point elsewhere. Restrict the file's ACL to your account. Do not set
`PGPASSWORD`, which is visible to other processes and persists in the
environment. See
[06-security/passwords-and-secrets.md](../06-security/passwords-and-secrets.md).

## Running tools: PowerShell vs CMD quirks

| Task | PowerShell | CMD | Notes |
|---|---|---|---|
| Run a SQL file | `psql -X -v ON_ERROR_STOP=1 -d DBNAME -f .\migration.sql` | `psql -X -v ON_ERROR_STOP=1 -d DBNAME -f migration.sql` | Use `-f`; PowerShell has no `<` input redirection (use `Get-Content .\migration.sql \| psql ...` if needed) |
| Backup | `pg_dump -Fc -d DBNAME -f .\appdb.dump` | `pg_dump -Fc -d DBNAME -f appdb.dump` | Always `-f`: Windows PowerShell 5.1's `>` writes UTF-16 and corrupts dumps. Flags: [pg-dump.md](pg-dump.md) |
| Single command with quotes | `psql -d DBNAME -c "SELECT 'x';"` | `psql -d DBNAME -c "SELECT 'x';"` | Use double quotes outside, single inside |
| Variable in SQL | `psql -d DBNAME -v tbl=app.orders -f q.sql` | same | `-c` does not expand `:tbl` ([psql.md](psql.md)) |
| `psql` meta-command | `psql -d DBNAME -c "\dt"` | `psql -d DBNAME -c "\dt"` | `\dt` is a psql meta-command, not SQL and not a PowerShell command |
| Create / drop DB | `createdb appdb` / `dropdb appdb` | same | `dropdb` is **destructive**: confirm with `psql -l`, back up first |

## Docker Desktop

PostgreSQL in a container on Windows uses the same Docker commands as any
host; see [docker.md](docker.md) and [12-docker/](../12-docker/). Notes:
publish the port (`-p 5432:5432`); use a named volume rather than a
bind-mounted Windows folder for the data directory (permission and
performance problems); `localhost:5432` may collide with a native
PostgreSQL Windows service on the same port.

## Troubleshooting

| Symptom | Check | Fix |
|---|---|---|
| `psql : The term 'psql' is not recognized` | `where.exe psql` | Add the `bin` directory to `PATH` or call the full path with `&` |
| `Start-Service` fails with access denied | Not elevated | Run PowerShell as Administrator |
| Service starts then stops | Data-directory log; Event Viewer | Read the newest log file; common causes: port in use (`netstat -ano \| findstr 5432`), bad `postgresql.conf` edit |
| `Test-NetConnection` true but `psql` fails | `pg_hba.conf`, `listen_addresses`, credentials | `psql` error text names the cause; [06-security/ssl.md](../06-security/ssl.md) |
| Garbled characters in SQL output | Console code page | Use a UTF-8 terminal; set `PGCLIENTENCODING=UTF8` |

Related: [psql.md](psql.md), [01-postgresql-cli/commands.md](../01-postgresql-cli/commands.md),
[15-production-runbooks/database-is-down.md](../15-production-runbooks/database-is-down.md).
