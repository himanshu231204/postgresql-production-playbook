# Health Check Scripts

Read-only checks for monitors, cron, and orchestrators. Concepts and
exit-code meaning: [../../14-observability/health-checks.md](../../14-observability/health-checks.md).

| Script | Purpose |
|---|---|
| `pg-health-check.sh` | `pg_isready` liveness, `SELECT 1` readiness, connection headroom, XID age, optional standby replay lag |

## Requirements

- Bash 4+ (uses `[[ =~ ]]`; the diagnostics script needs associative arrays)
- `pg_isready` and `psql` from any PostgreSQL 13+ client install in `PATH`
- A role with `CONNECT` and (for accurate connection counts across roles) `pg_monitor`

## Usage

```bash
export PGHOST=db.internal PGPORT=5432 PGUSER=monitoring PGDATABASE=postgres
export PGSSLMODE=verify-full                       # recommended for remote servers
# Credentials: ~/.pgpass, PGPASSFILE, or a secrets manager exporting PGPASSWORD
./pg-health-check.sh; echo "exit=$?"
```

Example outputs:

```text
OK: primary accepting connections; connections 4/100; max xid age 29
WARNING: connections 4/100 (4%)
CRITICAL: no response from server
UNKNOWN: pg_isready not found in PATH
```

## Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `PGHOST`, `PGPORT`, `PGUSER`, `PGDATABASE`, `PGSSLMODE`, ... | libpq defaults | Standard libpq connection settings |
| `CHECK_TIMEOUT` | `5` | Seconds for `pg_isready`, connect, and each query |
| `CONN_WARN_PCT` | `80` | WARNING at/above this percent of `max_connections` (illustrative default) |
| `XID_AGE_WARN` | `1000000000` | WARNING at/above this `age(datfrozenxid)` (illustrative default) |
| `REPL_LAG_WARN` | `0` | Standby only: WARNING at/above this many seconds of replay delay; `0` disables |

## Exit codes

`0` OK, `1` WARNING, `2` CRITICAL, `3` UNKNOWN.

## Safety

- Read-only: sessions set `default_transaction_read_only=on`; only `SELECT` statements run.
- No secrets stored or accepted as arguments; no values are interpolated into SQL (thresholds are validated as integers and compared in Bash).
- Counts only `backend_type = 'client backend'`; the `superuser_reserved_connections` slots are not subtracted.

## Validation status

Run against PostgreSQL 16: primary and streaming standby (OK, WARNING for
each threshold, standby lag WARNING), wrong role (CRITICAL), closed port
(CRITICAL), invalid threshold and missing tools (UNKNOWN). `shellcheck` was not
available in the validation environment and was not run. The `pg_isready` exit
code 1 (server rejecting connections) path was not reproduced.
