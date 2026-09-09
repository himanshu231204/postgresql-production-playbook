# Windows Command Reference

Everything below is PowerShell unless marked otherwise. For the *why*
behind service management and connecting, see
[01-postgresql-cli/commands.md](../01-postgresql-cli/commands.md) — this
page is the fast lookup, organized by OS instead of by topic.

## Service management

| Task | Command | Notes |
|---|---|---|
| Find the service name | `Get-Service postgresql*` | Name is version-suffixed, e.g. `postgresql-x64-16` |
| Check status | `Get-Service postgresql-x64-<ver>` | Does not confirm the server accepts connections — use `pg_isready` |
| Start | `Start-Service postgresql-x64-<ver>` | |
| Stop | `Stop-Service postgresql-x64-<ver>` | Drops every open connection |
| Restart | `Restart-Service postgresql-x64-<ver>` | |
| Set to start automatically | `Set-Service postgresql-x64-<ver> -StartupType Automatic` | Requires an elevated (Administrator) PowerShell session |

## Environment variables

| Task | Command | Notes |
|---|---|---|
| Set for the current session only | `$env:PGHOST = "localhost"` | Lost when the terminal closes |
| Set persistently for the current user | `setx PGPASSFILE "$env:USERPROFILE\.pgpass"` | Takes effect in **new** terminals only, not the current one |
| Set persistently (scriptable, same effect as `setx`) | `[Environment]::SetEnvironmentVariable("PGHOST", "localhost", "User")` | Third argument can be `"User"` or `"Machine"` (`"Machine"` needs Administrator) |
| Read a variable | `$env:PGHOST` | |

**Production note:** never use `setx`/`SetEnvironmentVariable` to store a
password — both write to the registry in plaintext, readable by any
process running as that user. Use a `.pgpass` file or a secrets manager
instead; see
[06-security/passwords-and-secrets.md](../06-security/passwords-and-secrets.md).

## Network diagnostics

Before assuming PostgreSQL itself is misbehaving, confirm the port is even
reachable:

```powershell
Test-NetConnection -ComputerName HOST -Port 5432
```

Check the `TcpTestSucceeded` field in the output. `$false` means the host
is unreachable or the port isn't listening/firewalled — a networking
problem, not necessarily a PostgreSQL problem. Compare against
`pg_isready`, which additionally confirms the PostgreSQL process itself is
accepting connections (see
[01-postgresql-cli/commands.md](../01-postgresql-cli/commands.md#checking-connectivity)).

## Running `psql`, `pg_dump`, `pg_restore`

If the PostgreSQL `bin` directory isn't on `PATH`, either add it
(`Get-Service postgresql*` won't tell you this — check the install
directory, typically `C:\Program Files\PostgreSQL\<version>\bin`) or call
the executables by full path, quoting because of the space in
`Program Files`:

```powershell
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -h localhost -U app_user -d app_db
```

See [psql.md](psql.md), [pg-dump.md](pg-dump.md), and
[pg-restore.md](pg-restore.md) for the flags themselves.

## Docker

Docker on Windows requires Docker Desktop with the WSL2 backend (the
Hyper-V backend is legacy). Once running, `docker`/`docker compose`
commands are identical to Linux/macOS — see [docker.md](docker.md).

## Common mistakes

- Running `setx` and expecting the current terminal to see the new value —
  it only applies to terminals opened afterward.
- Assuming a fixed service name across PostgreSQL versions — always
  confirm with `Get-Service postgresql*` first.
- Forgetting to quote paths containing spaces (`Program Files`) when
  calling `psql.exe`/`pg_dump.exe` by full path.
