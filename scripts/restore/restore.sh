#!/usr/bin/env bash
# Restore a backup set produced by scripts/backup/backup.sh into a database.
# Target: PostgreSQL 16 client tools.
#
# Usage: restore.sh /path/to/backup/set      (e.g. backups/appdb/20260101T020000Z)
#
# Required env:
#   TARGET_DB       database to restore into
# Connection (libpq variables; password via PGPASSFILE, never in this file):
#   PGHOST PGPORT PGUSER PGSSLMODE
# Optional env:
#   RESTORE_JOBS     parallel jobs (default: 4). Ignored with SINGLE_TXN=1.
#   SINGLE_TXN       1 = all-or-nothing restore in one transaction (default: 0)
#   NO_OWNER         1 = skip ownership (--no-owner), useful when roles differ
#   REPLACE_EXISTING 1 = DROP and recreate TARGET_DB if it exists. DESTRUCTIVE;
#                    also requires CONFIRM_DB_NAME=<same as TARGET_DB>.
#   VERIFY_SQL       optional SQL returning one value; printed after restore
#                    (example: "SELECT count(*) FROM orders")
#   PG_BIN_DIR       directory holding pg_restore etc. (default: use PATH)
# Roles: restoring globals.sql is NOT automatic. Review it, then apply it with
# psql before restoring if the target cluster lacks the roles the dump needs.
set -euo pipefail

SRC="${1:?usage: restore.sh /path/to/backup/set}"
: "${TARGET_DB:?TARGET_DB must be set}"
RESTORE_JOBS="${RESTORE_JOBS:-4}"
SINGLE_TXN="${SINGLE_TXN:-0}"
NO_OWNER="${NO_OWNER:-0}"
REPLACE_EXISTING="${REPLACE_EXISTING:-0}"
PG_BIN_DIR="${PG_BIN_DIR:-}"

bin() { if [[ -n "$PG_BIN_DIR" ]]; then echo "$PG_BIN_DIR/$1"; else echo "$1"; fi; }
log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2; }
die() { log "ERROR: $*"; exit 1; }

[[ "$TARGET_DB" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || die "TARGET_DB must be a simple identifier"
[[ "$RESTORE_JOBS" =~ ^[0-9]+$ ]] || die "RESTORE_JOBS must be an integer"
[[ -d "$SRC" ]] || die "backup set not found: $SRC"

# Locate the artifact inside the set.
artifact=""
for candidate in "$SRC"/*.dump "$SRC"/*.dir; do
  if [[ -e "$candidate" ]]; then artifact="$candidate"; break; fi
done
[[ -n "$artifact" ]] || die "no *.dump or *.dir found in $SRC"

# 1. Verify integrity before touching the target.
if [[ -f "$SRC/SHA256SUMS" ]]; then
  log "verifying checksums"
  ( cd "$SRC" && sha256sum --check --quiet SHA256SUMS ) || die "checksum mismatch; do not restore this set"
else
  log "WARNING: no SHA256SUMS in $SRC; integrity not verified"
fi

# 2. Prepare the target database.
exists="$("$(bin psql)" --no-psqlrc --tuples-only --no-align --dbname=postgres \
  --set=db="$TARGET_DB" <<< "SELECT 1 FROM pg_database WHERE datname = :'db'")"
if [[ "$exists" == "1" ]]; then
  [[ "$REPLACE_EXISTING" == 1 ]] || die "database $TARGET_DB already exists; restore into a new name, or set REPLACE_EXISTING=1 and CONFIRM_DB_NAME=$TARGET_DB"
  [[ "${CONFIRM_DB_NAME:-}" == "$TARGET_DB" ]] || die "REPLACE_EXISTING needs CONFIRM_DB_NAME=$TARGET_DB"
  log "DROPPING database $TARGET_DB (REPLACE_EXISTING=1)"
  "$(bin dropdb)" --if-exists "$TARGET_DB"
fi
log "creating database $TARGET_DB"
"$(bin createdb)" "$TARGET_DB"

# 3. Restore.
args=(--dbname="$TARGET_DB" --exit-on-error --no-password)
[[ "$NO_OWNER" == 1 ]] && args+=(--no-owner)
if [[ "$SINGLE_TXN" == 1 ]]; then
  args+=(--single-transaction)          # cannot be combined with --jobs
else
  args+=(--jobs="$RESTORE_JOBS")
fi
log "restoring $artifact -> $TARGET_DB"
"$(bin pg_restore)" "${args[@]}" "$artifact"

# 4. Refresh planner statistics (pg_restore does not carry them over).
"$(bin psql)" --no-psqlrc --dbname="$TARGET_DB" --command "ANALYZE"

if [[ -n "${VERIFY_SQL:-}" ]]; then
  log "verification query result:"
  "$(bin psql)" --no-psqlrc --tuples-only --no-align --dbname="$TARGET_DB" --command "$VERIFY_SQL"
fi
log "restore complete: $TARGET_DB"
