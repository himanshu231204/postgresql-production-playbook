#!/usr/bin/env bash
# Logical backup of one database plus cluster globals (roles, tablespaces).
# Target: PostgreSQL 16 client tools. Run as an OS user that can read the
# connection settings below; it needs only read access to the database
# (a dedicated backup role with pg_read_all_data is enough for pg_dump).
#
# Required env:
#   PGDATABASE      database to dump
# Connection (standard libpq variables; supply the password through
# PGPASSFILE or a secrets manager, never in this file):
#   PGHOST PGPORT PGUSER PGSSLMODE
# Optional env:
#   BACKUP_DIR      output root              (default: ./backups)
#   BACKUP_FORMAT   custom | directory       (default: custom)
#   DUMP_JOBS       parallel jobs, directory format only (default: 4)
#   RETENTION_DAYS  delete backup sets older than N days; 0 disables
#                   pruning (default: 7)
#   PG_BIN_DIR      directory holding pg_dump etc. (default: use PATH)
set -euo pipefail

: "${PGDATABASE:?PGDATABASE must be set}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
BACKUP_FORMAT="${BACKUP_FORMAT:-custom}"
DUMP_JOBS="${DUMP_JOBS:-4}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
PG_BIN_DIR="${PG_BIN_DIR:-}"

bin() { if [[ -n "$PG_BIN_DIR" ]]; then echo "$PG_BIN_DIR/$1"; else echo "$1"; fi; }
log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2; }

[[ "$RETENTION_DAYS" =~ ^[0-9]+$ ]] || { log "RETENTION_DAYS must be an integer"; exit 2; }
[[ "$DUMP_JOBS" =~ ^[0-9]+$ ]] || { log "DUMP_JOBS must be an integer"; exit 2; }
case "$BACKUP_FORMAT" in custom | directory) ;; *) log "BACKUP_FORMAT must be custom or directory"; exit 2 ;; esac

umask 077
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
set_dir="$BACKUP_DIR/$PGDATABASE/$stamp"
tmp_dir="$BACKUP_DIR/$PGDATABASE/.incomplete-$stamp"
mkdir -p "$tmp_dir"
trap 'rm -rf "$tmp_dir"' ERR INT TERM   # never leave a partial set that looks complete

log "dumping $PGDATABASE ($BACKUP_FORMAT) -> $set_dir"
if [[ "$BACKUP_FORMAT" == custom ]]; then
  "$(bin pg_dump)" --format=custom --file="$tmp_dir/$PGDATABASE.dump" "$PGDATABASE"
  artifact="$PGDATABASE.dump"
  list_target="$tmp_dir/$artifact"
else
  "$(bin pg_dump)" --format=directory --jobs="$DUMP_JOBS" --file="$tmp_dir/$PGDATABASE.dir" "$PGDATABASE"
  artifact="$PGDATABASE.dir"
  list_target="$tmp_dir/$artifact"
fi

# pg_dump does not include roles or tablespaces; dump them separately.
# --globals-only needs a role that can read pg_authid (superuser) on
# self-managed servers; on managed services it may be unavailable, in
# which case use --no-role-passwords or rebuild roles from IaC.
if [[ "${DUMP_GLOBALS:-1}" == 1 ]]; then
  "$(bin pg_dumpall)" --globals-only --file="$tmp_dir/globals.sql"
fi

# Verify the archive is readable: pg_restore --list parses the table of contents.
"$(bin pg_restore)" --list "$list_target" > "$tmp_dir/toc.txt"

# Checksums for every file in the set (portable across files and directories).
( cd "$tmp_dir" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS )

mv "$tmp_dir" "$set_dir"
trap - ERR INT TERM
log "backup complete: $set_dir"

# Retention: DESTRUCTIVE. Removes completed backup sets older than
# RETENTION_DAYS under this database's directory only.
if [[ "$RETENTION_DAYS" -gt 0 ]]; then
  find "$BACKUP_DIR/$PGDATABASE" -mindepth 1 -maxdepth 1 -type d \
    -name '[0-9]*T[0-9]*Z' -mtime +"$RETENTION_DAYS" -print -exec rm -rf {} + >&2 || true
fi

echo "$set_dir"
