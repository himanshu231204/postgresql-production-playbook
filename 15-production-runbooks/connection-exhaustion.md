# Runbook: Connection Exhaustion

Applies to PostgreSQL 16. Each client connection is a backend process;
`max_connections` is a hard ceiling set at server start (changing it needs
a restart).

## Symptoms

| Error text | Meaning |
|---|---|
| `FATAL: sorry, too many clients already` | All `max_connections` slots are used (including the reserved ones) |
| `FATAL: remaining connection slots are reserved for roles with the SUPERUSER attribute` | Only the `superuser_reserved_connections` slots are left; ordinary roles are refused. **Seen first**, and reproduced in testing with `max_connections=10`, `superuser_reserved_connections=3` |
| `FATAL: too many connections for role "x"` / `... for database "x"` | Per-role or per-database `CONNECTION LIMIT` hit |
| Pool timeouts in the app (`QueuePool limit ... reached`, `timeout expired`) | Pool is starved; may or may not be the server limit |

Superusers keep working while ordinary roles are refused: that is the
reserved headroom. Use it for diagnosis; do not let applications connect as
superuser.

## Triage (first 2 minutes)

Connect as an administrator (SQL). If even that fails with `too many
clients`, see [Cannot connect at all](#cannot-connect-at-all).

```sql
SELECT count(*)                                  AS client_backends,
       current_setting('max_connections')::int   AS max_connections,
       current_setting('superuser_reserved_connections')::int AS superuser_reserved
FROM pg_stat_activity
WHERE backend_type = 'client backend';
```

`max_connections` counts client connections; autovacuum workers,
walsenders and other background processes are accounted separately, which
is why filtering on `backend_type = 'client backend'` is the number that
matters for applications.

Then decide:

| What dominates the list (next query) | Likely cause | Go to |
|---|---|---|
| Many `idle` from one app | Pool sized too large, or too many app replicas x pool size | [Remediation A](#a-reduce-the-load-on-the-slots) |
| Many `idle in transaction` | App opened a transaction and did not commit (bug, long external call inside a txn) | [Remediation B](#b-clear-idle-in-transaction-sessions) |
| Many `active`, most waiting on `Lock` | Lock pile-up holding connections | [lock-contention.md](lock-contention.md) |
| Many `active`, CPU saturated | Slow queries holding slots | [slow-query.md](slow-query.md) |
| Sudden spike right after a deploy or restart | Reconnect storm / pool misconfiguration | [Remediation A](#a-reduce-the-load-on-the-slots) |

## Diagnosis

Requires `pg_monitor` or superuser to see other roles' queries; ordinary
roles see only their own sessions' details.

**Who is using the connections** (SQL): group by role, application, state.

```sql
SELECT usename,
       application_name,
       state,
       count(*)                       AS sessions,
       max(now() - state_change)      AS longest_in_state
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY usename, application_name, state
ORDER BY sessions DESC;
```

`application_name` is set by the client (`?application_name=api-worker` in
the connection string, or `SET application_name`). If everything reads
empty, that is itself the first prevention task.

**Idle-in-transaction sessions** (they hold locks and block vacuum, and
they are not reclaimed by the pool):

```sql
SELECT pid, usename, application_name, client_addr,
       now() - xact_start    AS xact_age,
       now() - state_change  AS idle_for,
       left(query, 80)       AS last_query
FROM pg_stat_activity
WHERE state IN ('idle in transaction', 'idle in transaction (aborted)')
ORDER BY xact_start;
```

`query` shows the **last** statement the session ran, not what it is
waiting for: it points you to the code path that opened the transaction.

**Connections per database and per client host** (SQL):

```sql
SELECT datname, client_addr, count(*) AS sessions
FROM pg_stat_activity
WHERE backend_type = 'client backend'
GROUP BY datname, client_addr
ORDER BY sessions DESC;
```

**Limits in effect** (SQL):

```sql
SHOW max_connections;
SHOW superuser_reserved_connections;
SELECT rolname, rolconnlimit, rolconfig FROM pg_roles WHERE rolconnlimit <> -1 OR rolconfig IS NOT NULL;
SELECT datname, datconnlimit FROM pg_database WHERE datconnlimit <> -1;
```

`rolconnlimit = -1` means no per-role limit.

## Remediation (ordered, safest first)

### A. Reduce the load on the slots

1. **Stop the source.** Scale down the app deployment, pause the worker/batch/cron that is consuming the slots, or restart only the misbehaving app so it releases its pool cleanly. This is reversible and does not touch the database.
2. **Lower the pool size** or replica count so `replicas x pool_size` (plus overflow) stays below `max_connections - superuser_reserved_connections - headroom for admin, monitoring, replication`.
3. **Cap the offender** so it cannot starve others (SQL; affects **new** sessions of that role):

```sql
ALTER ROLE batch_user CONNECTION LIMIT 10;   -- -1 removes the limit again
```

### B. Clear idle-in-transaction sessions

Prefer the targeted route: fix the app. If sessions are stuck and are
blocking others, cancel first, then terminate.

`pg_cancel_backend(pid)` cancels the **running query** and leaves the
session. It does nothing to a session that is `idle in transaction`
(reproduced: it returned `t` and the state stayed the same), so for those
you need terminate.

#### `pg_terminate_backend` (destructive, read first)

- **What it does:** closes the session; its open transaction is rolled back and the client gets `terminating connection due to administrator command`.
- **Why risky:** uncommitted work is lost; applications that do not retry or reconnect will error; terminating a session that is mid-way through a multi-step business operation can leave external side effects (emails sent, payments called) without the database record.
- **Safer alternative:** `pg_cancel_backend(pid)` for active queries; fix the code path; set `idle_in_transaction_session_timeout` (below) so PostgreSQL does it consistently.
- **Precaution:** confirm the target (pid, user, application, last query) in the same query you terminate with; start with one pid, not a bulk filter; inform application owners; never terminate your own session or replication/autovacuum backends (the filter on `backend_type` and `pid <> pg_backend_pid()` below).

Terminate one session after you inspected it (SQL):

```sql
SELECT pg_terminate_backend(<PID>);
```

Bulk terminate idle-in-transaction sessions older than a threshold for
**one named application**, only after reviewing the list above (SQL):

```sql
SELECT pid, usename, application_name, pg_terminate_backend(pid) AS terminated
FROM pg_stat_activity
WHERE backend_type = 'client backend'
  AND pid <> pg_backend_pid()
  AND state = 'idle in transaction'
  AND application_name = 'batch-job'
  AND now() - state_change > interval '10 minutes';
```

Narrow `application_name`/`usename` first; running this with no application
filter disconnects every well-behaved client with an open transaction too.

### C. Set automatic guards (prevents recurrence, applies to new sessions)

```sql
-- per role (safest scope; takes effect on the role's next connection)
ALTER ROLE app_user SET idle_in_transaction_session_timeout = '5min';
ALTER ROLE app_user SET statement_timeout = '30s';
ALTER ROLE app_user SET lock_timeout = '5s';
```

Cluster-wide alternative (needs superuser; applies after reload, no restart):

```sql
ALTER SYSTEM SET idle_in_transaction_session_timeout = '10min';
SELECT pg_reload_conf();
```

Values are illustrative; pick them from your workload's real transaction
durations. A timeout that is too short breaks legitimate long jobs: apply
it per role, and give batch roles a different value. Confirm in a **new**
session with `SHOW idle_in_transaction_session_timeout;`.

### D. Raise `max_connections` (last resort, needs restart)

Raising it spends memory and increases contention (every backend is a
process, and snapshot cost grows with connection count); it rarely fixes
the underlying problem. Do this only after A to C, in a maintenance window:

```sql
ALTER SYSTEM SET max_connections = 200;   -- written to postgresql.auto.conf
```

then restart the server (see [database-is-down.md](database-is-down.md)
for start/stop commands). `SELECT name, setting, pending_restart FROM
pg_settings WHERE name = 'max_connections';` shows `pending_restart = t`
until it is applied. A restart drops every connection: announce it.

The sustainable fix is a pooler: [05-performance/connection-pooling.md](../05-performance/connection-pooling.md).

### Cannot connect at all

If a superuser cannot connect either (`too many clients already`), the
reserved slots are consumed too. Options, safest first:

1. Stop the app tier / pause jobs, wait seconds for connections to close, reconnect.
2. Connect through the local Unix socket as `postgres` (OS user): `sudo -u postgres psql` (Unix shell). Reserved slots only help roles with the `SUPERUSER` attribute (PostgreSQL 16 also supports `reserved_connections` and the `pg_use_reserved_connections` role for non-superusers).
3. On a managed service, use the provider's admin/console connection or reboot the instance (all connections drop).

## Verification

```sql
SELECT count(*) AS client_backends,
       current_setting('max_connections')::int AS max_connections
FROM pg_stat_activity WHERE backend_type = 'client backend';
```

- [ ] `client_backends` stable and well below `max_connections - superuser_reserved_connections`.
- [ ] No `idle in transaction` older than a few minutes (query above returns 0 rows or only young ones).
- [ ] Application error rate and pool wait time back to baseline.
- [ ] No new `too many clients` in the log.

## Prevention

| Control | Why | Where |
|---|---|---|
| Connection pooler (PgBouncer or a managed pooler) | Many app connections multiplex onto few server connections | [05-performance/connection-pooling.md](../05-performance/connection-pooling.md) |
| App pool sized from a budget: `replicas x (pool_size + max_overflow)` < available slots | The common cause is autoscaling multiplying pool size | [08-python-fastapi/](../08-python-fastapi/) |
| `idle_in_transaction_session_timeout` per role | Stuck transactions are killed by the server, with a log entry | above |
| `application_name` set by every service | Makes the diagnosis query actionable | above |
| Separate roles with `CONNECTION LIMIT` for batch/analytics | One workload cannot starve the API | above |
| Alert at a fraction of the ceiling (example: sustained above 80% of non-reserved slots) | Time to act before the outage. Threshold is illustrative; tune to your baseline | [14-observability/monitoring.md](../14-observability/monitoring.md) |

Tradeoff: a transaction-mode pooler cannot keep session state (session
`SET`, advisory locks, temp tables, `LISTEN`, some prepared-statement
setups); see the pooling page before changing mode.

## Escalation / When to stop

- Connection count keeps climbing after the app is scaled to zero: something else connects (replication tooling, a forgotten service, an attack). Check `client_addr` and `pg_hba.conf`; engage security.
- Sessions will not terminate (`pg_terminate_backend` returns `t` but the row remains for more than a few seconds): the backend is stuck in the kernel (I/O). Engage platform/infra; a restart may be required.
- Raising `max_connections` is being proposed as the first fix: stop, apply A to C first.
