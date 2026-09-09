# PostgreSQL CLI

## What it is

This section covers the command-line surface for working with PostgreSQL
directly: connecting with `psql`, the meta-commands available once
connected, and starting/stopping/checking the server process itself on
Windows, macOS, and Linux.

## Why it matters

Every other section in this repository assumes you can already connect to
a PostgreSQL server and confirm whether it's running. This is the
prerequisite skill, and it's also the first thing you reach for during an
incident — before `EXPLAIN ANALYZE`, before checking `pg_stat_activity`,
before restoring a backup, you need `psql` to work.

## In this section

- [commands.md](commands.md) — connecting with `psql`, psql meta-commands
  (`\l`, `\c`, `\dt`, `\d`, `\dn`, `\du`, `\dx`, `\conninfo`, `\timing`,
  `\x`, `\q`, and more), OS-specific service management, `pg_ctl`, and
  `pg_isready`.
- [examples/](examples/) — runnable connectivity-check scripts and an
  annotated `.psqlrc` sample.

## 60-second example

```
psql -h localhost -p 5432 -U app_user -d app_db
```

Once connected:

```
app_db=> \conninfo
You are connected to database "app_db" as user "app_user" on host "localhost" at port "5432".
app_db=> \dt
app_db=> \q
```

See [commands.md](commands.md) for the full command and meta-command
reference.

## Where to go next

- Not sure the server is even running? [commands.md](commands.md#checking-connectivity)
  covers `pg_isready` and service status checks.
- Running PostgreSQL in Docker instead of natively? See
  [12-docker/](../12-docker/).
- Need the broader OS-by-OS command tables (not just PostgreSQL)? See
  [16-command-reference/](../16-command-reference/).
- Ready to write queries? Continue to
  [02-sql-fundamentals/](../02-sql-fundamentals/).
- Setting up roles and least-privilege access? See
  [06-security/roles.md](../06-security/roles.md).
