#!/usr/bin/env bash
# pg-health-check.sh - read-only PostgreSQL health check for monitors / cron.
#
# Exit codes (Nagios-style, usable by most monitors):
#   0 OK        1 WARNING        2 CRITICAL        3 UNKNOWN (bad config / missing tools)
#
# Connection: libpq environment variables (PGHOST, PGPORT, PGUSER, PGDATABASE,
# PGPASSFILE, PGSSLMODE, ...). No password is read or accepted by this script;
# use ~/.pgpass, PGPASSFILE, or a secrets manager that exports PGPASSWORD.
#
# Thresholds (illustrative defaults - tune per system, see 14-observability/health-checks.md):
#   CONN_WARN_PCT   connections / max_connections percent        (default 80)
#   XID_AGE_WARN    max age(datfrozenxid) in transactions        (default 1000000000)
#   REPL_LAG_WARN   replay lag in seconds on a standby, 0 = skip (default 0)
#   CHECK_TIMEOUT   seconds for pg_isready and each query        (default 5)
set -euo pipefail

CONN_WARN_PCT="${CONN_WARN_PCT:-80}"
XID_AGE_WARN="${XID_AGE_WARN:-1000000000}"
REPL_LAG_WARN="${REPL_LAG_WARN:-0}"
CHECK_TIMEOUT="${CHECK_TIMEOUT:-5}"

for tool in pg_isready psql; do
  command -v "$tool" >/dev/null 2>&1 || { echo "UNKNOWN: $tool not found in PATH"; exit 3; }
done
for var in CONN_WARN_PCT XID_AGE_WARN REPL_LAG_WARN CHECK_TIMEOUT; do
  [[ "${!var}" =~ ^[0-9]+$ ]] || { echo "UNKNOWN: $var must be a non-negative integer"; exit 3; }
done

status=0
messages=()
raise() { # raise <level 1|2> <message>
  messages+=("$2")
  (( $1 > status )) && status=$1
  return 0
}

# --- Level 1: liveness (is the server accepting connections?) -------------
# pg_isready: 0 accepting, 1 rejecting (startup/shutdown), 2 no response, 3 no attempt (bad params)
rc=0
pg_isready -t "$CHECK_TIMEOUT" >/dev/null || rc=$?
case "$rc" in
  0) ;;
  1) echo "CRITICAL: server rejecting connections (starting up, shutting down, or recovery not yet consistent)"; exit 2 ;;
  2) echo "CRITICAL: no response from server"; exit 2 ;;
  *) echo "UNKNOWN: pg_isready made no attempt (rc=$rc); check PG* variables"; exit 3 ;;
esac

# Run one read-only query; -X ignores ~/.psqlrc, ON_ERROR_STOP aborts on error.
q() { # q <sql> [psql -v args...]
  local sql="$1"; shift
  PGCONNECT_TIMEOUT="$CHECK_TIMEOUT" PGOPTIONS="-c default_transaction_read_only=on -c statement_timeout=${CHECK_TIMEOUT}000" \
    psql -X -qAt -v ON_ERROR_STOP=1 "$@" -c "$sql"
}

# --- Level 2: readiness (can we authenticate and run a query?) -------------
if ! q "SELECT 1" >/dev/null 2>&1; then
  echo "CRITICAL: server up but cannot authenticate / run SELECT 1"
  exit 2
fi

in_recovery="$(q "SELECT pg_is_in_recovery()")"

# --- Connection saturation -------------------------------------------------
# Counts client backends only; superuser_reserved_connections are not subtracted here.
read -r used max < <(q "SELECT count(*), current_setting('max_connections')::int
                        FROM pg_stat_activity WHERE backend_type = 'client backend'" | tr '|' ' ')
pct=$(( used * 100 / max ))
if (( pct >= CONN_WARN_PCT )); then raise 1 "connections ${used}/${max} (${pct}%)"; fi

# --- Transaction ID age (wraparound protection) ----------------------------
xid_age="$(q "SELECT max(age(datfrozenxid)) FROM pg_database")"
if (( xid_age >= XID_AGE_WARN )); then raise 1 "max datfrozenxid age ${xid_age}"; fi

# --- Replication lag (standby only, opt-in) --------------------------------
if [[ "$in_recovery" == "t" && "$REPL_LAG_WARN" -gt 0 ]]; then
  lag="$(q "SELECT COALESCE(EXTRACT(EPOCH FROM now() - pg_last_xact_replay_timestamp())::bigint, -1)")"
  if (( lag < 0 )); then
    raise 1 "standby has not replayed any transaction yet (lag unknown)"
  elif (( lag >= REPL_LAG_WARN )); then
    raise 1 "replay lag ${lag}s"
  fi
fi

role="primary"; [[ "$in_recovery" == "t" ]] && role="standby"
if (( status == 0 )); then
  echo "OK: ${role} accepting connections; connections ${used}/${max}; max xid age ${xid_age}"
else
  echo "$([[ $status == 2 ]] && echo CRITICAL || echo WARNING): ${messages[*]}"
fi
exit "$status"
