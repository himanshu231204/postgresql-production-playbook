#!/usr/bin/env bash
# pg-diagnostics.sh - read-only diagnostic report for a PostgreSQL 13+ server.
#
# Usage: pg-diagnostics.sh [section ...]
#   sections: activity blockers idle-in-tx slow-queries db-stats tables sizes replication xid-age
#   no argument = all sections. pg_stat_statements output needs the extension in the current database.
#
# Connection: libpq PG* environment variables only; no secrets handled here.
# Tunables (integers, passed to psql as variables, never string-interpolated):
#   MIN_SECONDS  minimum age in seconds for long-running / idle-in-tx rows (default 30)
#   ROW_LIMIT    rows per section                                            (default 20)
# Every statement runs in a read-only session with a statement_timeout.
set -euo pipefail

MIN_SECONDS="${MIN_SECONDS:-30}"
ROW_LIMIT="${ROW_LIMIT:-20}"
for var in MIN_SECONDS ROW_LIMIT; do
  [[ "${!var}" =~ ^[0-9]+$ ]] || { echo "error: $var must be a non-negative integer" >&2; exit 3; }
done
command -v psql >/dev/null 2>&1 || { echo "error: psql not found in PATH" >&2; exit 3; }

export PGOPTIONS="${PGOPTIONS:-} -c default_transaction_read_only=on -c statement_timeout=30000"
export PGAPPNAME="${PGAPPNAME:-pg-diagnostics}"

run() { # run <title> <sql>
  printf '\n=== %s ===\n' "$1"
  # SQL goes via stdin: psql expands :variables there, but not with -c.
  printf '%s;\n' "$2" | psql -X -v ON_ERROR_STOP=1 -v min_seconds="$MIN_SECONDS" -v row_limit="$ROW_LIMIT" -P pager=off -f -
}

sec_activity() { run "Sessions by state / wait event" "
SELECT backend_type, state, wait_event_type, wait_event, count(*)
FROM pg_stat_activity
GROUP BY 1,2,3,4
ORDER BY count(*) DESC"; }

sec_blockers() { run "Blocked sessions and their blockers" "
SELECT blocked.pid AS blocked_pid, blocker.pid AS blocking_pid,
       now() - blocked.query_start AS blocked_for,
       blocked.wait_event_type, blocker.state AS blocker_state,
       left(blocked.query, 80) AS blocked_query, left(blocker.query, 80) AS blocker_last_query
FROM pg_stat_activity blocked
JOIN LATERAL unnest(pg_blocking_pids(blocked.pid)) AS b(pid) ON true
JOIN pg_stat_activity blocker ON blocker.pid = b.pid
ORDER BY blocked_for DESC"; }

sec_idle_in_tx() { run "Idle-in-transaction and long transactions (>= MIN_SECONDS)" "
SELECT pid, usename, application_name, state,
       now() - xact_start AS xact_age, now() - state_change AS in_state_for,
       left(query, 80) AS last_query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL AND pid <> pg_backend_pid()
  AND now() - xact_start >= make_interval(secs => :min_seconds)
ORDER BY xact_start
LIMIT :row_limit"; }

sec_slow() { run "Top statements by total execution time (pg_stat_statements, PG13+ columns)" "
SELECT queryid, calls, round(total_exec_time::numeric, 1) AS total_ms,
       round(mean_exec_time::numeric, 2) AS mean_ms, rows, left(query, 80) AS query
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT :row_limit"; }

sec_db() { run "Database counters since stats_reset" "
SELECT datname, numbackends, xact_commit, xact_rollback, deadlocks, temp_files,
       pg_size_pretty(temp_bytes) AS temp_bytes,
       round(100.0 * blks_hit / NULLIF(blks_hit + blks_read, 0), 2) AS cache_hit_pct,
       stats_reset
FROM pg_stat_database
WHERE datname IS NOT NULL
ORDER BY datname"; }

sec_tables() { run "Tables: dead tuples and scan mix" "
SELECT schemaname, relname, n_live_tup, n_dead_tup, seq_scan, idx_scan,
       last_autovacuum, last_autoanalyze
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT :row_limit"; }

sec_sizes() { run "Largest relations (total size incl. indexes/TOAST)" "
SELECT n.nspname AS schema, c.relname AS name,
       pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size,
       pg_size_pretty(pg_relation_size(c.oid)) AS table_size
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r','m') AND n.nspname NOT IN ('pg_catalog','information_schema','pg_toast')
ORDER BY pg_total_relation_size(c.oid) DESC
LIMIT :row_limit"; }

sec_replication() { run "Replication (primary: pg_stat_replication; standby: replay delay)" "
SELECT application_name, client_addr, state, sync_state,
       pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS replay_lag_bytes, replay_lag
FROM pg_stat_replication
WHERE NOT pg_is_in_recovery()
UNION ALL
SELECT 'standby', NULL, 'in_recovery', NULL, NULL,
       now() - pg_last_xact_replay_timestamp()
WHERE pg_is_in_recovery()"; }

sec_xid() { run "Transaction ID age per database" "
SELECT datname, age(datfrozenxid) AS xid_age, mxid_age(datminmxid) AS mxid_age
FROM pg_database
ORDER BY age(datfrozenxid) DESC"; }

declare -A SECTIONS=(
  [activity]=sec_activity [blockers]=sec_blockers [idle-in-tx]=sec_idle_in_tx
  [slow-queries]=sec_slow [db-stats]=sec_db [tables]=sec_tables
  [sizes]=sec_sizes [replication]=sec_replication [xid-age]=sec_xid
)
ORDER=(activity blockers idle-in-tx slow-queries db-stats tables sizes replication xid-age)

(( $# > 0 )) && ORDER=("$@")
for s in "${ORDER[@]}"; do
  [[ -n "${SECTIONS[$s]:-}" ]] || { echo "error: unknown section '$s'" >&2; exit 3; }
done
for s in "${ORDER[@]}"; do "${SECTIONS[$s]}"; done
