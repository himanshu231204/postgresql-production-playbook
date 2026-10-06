# Health Checks

PostgreSQL 16 client tools. The script described here is
[../scripts/health-check/pg-health-check.sh](../scripts/health-check/README.md);
it was run against a local primary and standby, including failure paths.

## What it is

A fast, read-only probe that tells a load balancer, orchestrator, or
monitor whether PostgreSQL is usable.

## Why it matters

"Port open" and "database usable" are different. A server can accept TCP
connections while rejecting logins (startup, crash recovery, shutdown) or
while out of connection slots. Orchestrators that restart on failure need
the cheapest check that is still honest; alerting needs a deeper one.

## Levels

| Level | Question | Check | Cost |
|---|---|---|---|
| Liveness | Is a PostgreSQL server answering? | `pg_isready` | Opens a connection attempt but does not authenticate or run a query |
| Readiness | Can a client connect, authenticate, and run a query? | `psql -c 'SELECT 1'` | One real connection |
| Health (degraded) | Is it in a safe operating state? | Connection headroom, XID age, replica lag, free disk | A few catalog queries |

Use liveness for "should the process be restarted"; use readiness for
"should this instance receive traffic"; use the degraded checks for
alerting. Do not restart a database because a *degraded* check fails:
restarting a saturated or lagging server usually makes things worse.
Use a read-only role and keep the check's timeout short.

## pg_isready

`pg_isready` is a **PostgreSQL client utility (Unix shell / Windows
CMD / PowerShell, same flags)**; it sends a connection attempt and reports
status. Syntax:

```bash
pg_isready -h HOST -p 5432 -d DATABASE -U USER -t 5
```

| Exit code | Meaning (PostgreSQL docs) |
|---|---|
| `0` | Server accepting connections normally |
| `1` | Server rejecting connections (for example during startup or shutdown) |
| `2` | No response to the connection attempt |
| `3` | No attempt made (for example, invalid parameters) |

Verified here: `0` on a running server, `2` for a closed port, `3` for
an invalid connection option (`pg_isready -d "bad=conn"`). `1` and `3`
come from the PostgreSQL documentation; `1` was not reproduced locally.
`-t` is the timeout in seconds (default 3, `0` disables). It does not
check credentials or database existence; a `0` does not prove a login
will succeed.

## Readiness query

```bash
psql -X -qAt -v ON_ERROR_STOP=1 -c "SELECT 1"
```

`-X` ignores `~/.psqlrc`; `-q` quiet; `-A -t` unaligned, tuples only;
`ON_ERROR_STOP` makes psql exit non-zero on error. Set connection details
via libpq variables (`PGHOST`, `PGPORT`, `PGUSER`, `PGDATABASE`,
`PGCONNECT_TIMEOUT`, `PGSSLMODE`) and credentials via `~/.pgpass` /
`PGPASSFILE` or the secrets manager; do not put a password in the
command line. See [../01-postgresql-cli/](../01-postgresql-cli/README.md).

For a **primary-only** or **standby-only** target:

```sql
SELECT pg_is_in_recovery();   -- f on a primary, t on a standby
```

## The script

```bash
PGHOST=db.internal PGUSER=monitoring PGDATABASE=postgres \
  ./scripts/health-check/pg-health-check.sh
echo $?
```

Exit codes (Nagios plugin convention, accepted by most monitors):

| Code | State | Examples |
|---|---|---|
| 0 | OK | All checks pass |
| 1 | WARNING | Connection usage at/above `CONN_WARN_PCT`; XID age at/above `XID_AGE_WARN`; standby replay lag at/above `REPL_LAG_WARN` |
| 2 | CRITICAL | `pg_isready` returns 1 or 2; cannot authenticate / run `SELECT 1` |
| 3 | UNKNOWN | `psql`/`pg_isready` missing, invalid threshold, `pg_isready` made no attempt |

Verified paths: OK on primary and standby, each WARNING condition,
auth failure (wrong role) = 2, closed port = 2, bad `CHECK_TIMEOUT` = 3,
missing tools = 3. All SQL runs with
`default_transaction_read_only=on` and a `statement_timeout`.

The default thresholds are **illustrative** (80% of connections, 1 billion
XID age, replica lag check off); set them from your own baseline. The
standby lag check uses `now() - pg_last_xact_replay_timestamp()`, which
grows when the primary has no write traffic; on a quiet system combine
it with LSN comparison ([monitoring.md](monitoring.md)).

## Kubernetes / container notes

For a probe, `pg_isready` alone is a reasonable liveness probe; use the
script (or a `SELECT 1`) as the readiness probe. For a Docker Compose
`healthcheck` using `pg_isready`, see [../12-docker/](../12-docker/README.md).

## Common mistakes

- Using a TCP port check as the health check.
- Making the liveness probe heavy (queries that fail under load cause restarts, which worsen load).
- Putting a password on the command line or in the script.
- Running the check as a superuser, or against a database that application roles cannot see.
- Treating replica lag as a liveness failure.

## Quick revision

- Liveness = `pg_isready` (exit 0/1/2/3); readiness = a real query; health = headroom/lag/XID age.
- Exit codes 0/1/2/3 map to OK/WARNING/CRITICAL/UNKNOWN in the script.
- Thresholds are yours to set; the defaults are examples.
- Connection settings come from `PG*` variables; credentials from `~/.pgpass` or a secrets manager.
