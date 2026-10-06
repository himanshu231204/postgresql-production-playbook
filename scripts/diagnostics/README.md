# Diagnostics Scripts

Read-only reports for investigating a live server. Query explanations:
[../../14-observability/](../../14-observability/README.md).

| Script | Purpose |
|---|---|
| `pg-diagnostics.sh` | Prints sessions by state/wait event, blocked sessions and blockers, long/idle-in-transaction sessions, top `pg_stat_statements`, database counters, table stats, largest relations, replication, XID age |

## Usage

```bash
export PGHOST=db.internal PGUSER=monitoring PGDATABASE=app
./pg-diagnostics.sh                       # all sections
./pg-diagnostics.sh blockers idle-in-tx   # selected sections
MIN_SECONDS=60 ROW_LIMIT=10 ./pg-diagnostics.sh idle-in-tx
```

Sections: `activity`, `blockers`, `idle-in-tx`, `slow-queries`,
`db-stats`, `tables`, `sizes`, `replication`, `xid-age`.

| Variable | Default | Meaning |
|---|---|---|
| `PG*` | libpq defaults | Connection settings; credentials via `~/.pgpass`/`PGPASSFILE`/secrets manager |
| `MIN_SECONDS` | `30` | Minimum transaction age for `idle-in-tx` rows |
| `ROW_LIMIT` | `20` | Rows per section |

Exit code: `0` success, `3` bad argument/config, otherwise `psql`'s non-zero code
(for example when `pg_stat_statements` is not installed in the database).

## Safety

- Read-only: `default_transaction_read_only=on`, `statement_timeout=30s`; no cancel/terminate/reset calls are made. Acting on what you find is a manual step with the precautions in [../../14-observability/pg-stat-activity.md](../../14-observability/pg-stat-activity.md).
- `MIN_SECONDS` and `ROW_LIMIT` are validated as integers and passed as psql variables (`:min_seconds`, `:row_limit`), never concatenated into SQL.
- Query text in output may contain sensitive literals (statements are shown as stored; `pg_stat_statements` normalizes constants, `pg_stat_activity` does not). Treat the output as sensitive.
- Run as a `pg_monitor` member; without it, other roles' sessions show NULL columns.

## Validation status

Executed against PostgreSQL 16 with a reproduced lock-blocking scenario and an
idle-in-transaction session; all sections returned expected rows, invalid
arguments exit `3`. `shellcheck` was not available and was not run.
