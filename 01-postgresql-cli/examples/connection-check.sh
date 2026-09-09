#!/usr/bin/env bash
# Verify PostgreSQL connectivity using only PG* environment variables.
# No credentials are read from arguments or hardcoded here.
#
# Required env vars: none (libpq defaults apply if unset).
# Optional env vars: PGHOST, PGPORT, PGUSER, PGDATABASE, PGPASSFILE.
# Usage: PGHOST=localhost PGPORT=5432 PGUSER=app_user PGDATABASE=app_db ./connection-check.sh

set -euo pipefail

echo "Checking whether the PostgreSQL server is accepting connections..."
if ! pg_isready; then
    echo "pg_isready reported the server is not accepting connections (see exit code)." >&2
    exit 1
fi

echo "Server is accepting connections. Fetching connection info..."
psql -X -q -c '\conninfo'
