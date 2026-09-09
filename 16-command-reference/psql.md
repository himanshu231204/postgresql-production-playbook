# `psql` Command-Line Reference

This page covers **flags for invoking `psql` from a shell or script** —
for automation, CI, and one-off scripting. For the interactive meta-commands
you type once already connected (`\dt`, `\d`, `\du`, `\conninfo`, etc.),
see [01-postgresql-cli/commands.md](../01-postgresql-cli/commands.md) — that
page owns the full meta-command reference; it isn't repeated here.

## Running a single command

```bash
psql -h HOST -U USER -d DBNAME -c "SELECT 1;"
```

`-c` runs one command (SQL or a meta-command) and exits — no interactive
prompt. Multiple `-c` flags run in sequence, each in its own implicit
transaction unless `-1` is also given.

## Running a script file

```bash
psql -h HOST -U USER -d DBNAME -f migration.sql
```

## Scripting-oriented flags

| Flag | Purpose | Production notes |
|---|---|---|
| `-c "SQL"` | Run one command, then exit | |
| `-f file.sql` | Run a script file, then exit | The file is read by `psql` on the client; statements still execute on the server |
| `-1` / `--single-transaction` | Wrap the whole script/command list in one transaction | If any statement fails, everything rolls back — use for migrations you want all-or-nothing |
| `-v NAME=value` | Set a `psql` variable, referenced as `:NAME` inside SQL/scripts | |
| `-v ON_ERROR_STOP=1` | Stop the script on the first error instead of continuing | **Always set this for automated/CI scripts** — without it, `psql` keeps running past a failed statement and can leave a script half-applied while still looking like it "ran" |
| `-A` | Unaligned output (no padding) | Combine with `-t` and `-F` for machine-parseable output |
| `-t` | Tuples only — suppress column headers and row-count footer | |
| `-F sep` | Field separator for unaligned output | |
| `--csv` | CSV output | |
| `-X` | Skip reading `~/.psqlrc` | Use in scripts so a developer's local `.psqlrc` can't change script behavior |
| `-q` | Quiet — suppress informational messages | |
| `-l` | List databases and exit (script-friendly form of `\l`) | |
| `-V` / `--version` | Print `psql`'s version and exit | |

## Exit status

Automation should check this, not just stdout:

| Exit code | Meaning |
|---|---|
| `0` | Completed normally |
| `1` | A fatal error in `psql` itself (e.g. out of memory, script file not found) |
| `2` | The connection to the server failed, in a non-interactive session |
| `3` | A script error occurred **and** `ON_ERROR_STOP` was set |

Exit code `3` only happens with `ON_ERROR_STOP` set — without it, a failed
statement inside a script does not make `psql` exit non-zero, which is why
CI/deploy scripts should always pass `-v ON_ERROR_STOP=1`.

## Example: safe migration-style invocation for automation

```bash
psql -h "$PGHOST" -U "$PGUSER" -d "$PGDATABASE" \
     -v ON_ERROR_STOP=1 \
     -X -q \
     -f migration.sql
echo "Exit code: $?"
```

## Common mistakes

- Running a script in CI without `-v ON_ERROR_STOP=1` — a failed statement
  doesn't fail the build, it just gets silently skipped.
- Relying on `psql`'s default exit code alone to detect a mid-script
  failure without `ON_ERROR_STOP` set — it won't be non-zero.
- Parsing the default aligned/bordered output instead of using
  `-A -t -F`/`--csv` for anything a script needs to read.
