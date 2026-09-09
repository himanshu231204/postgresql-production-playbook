# Verify PostgreSQL connectivity using only PG* environment variables.
# No credentials are read from arguments or hardcoded here.
#
# Required env vars: none (libpq defaults apply if unset).
# Optional env vars: $env:PGHOST, $env:PGPORT, $env:PGUSER, $env:PGDATABASE, $env:PGPASSFILE.
# Usage:
#   $env:PGHOST = "localhost"; $env:PGPORT = "5432"; $env:PGUSER = "app_user"; $env:PGDATABASE = "app_db"
#   .\connection-check.ps1

$ErrorActionPreference = "Stop"

Write-Host "Checking whether the PostgreSQL server is accepting connections..."
pg_isready
if ($LASTEXITCODE -ne 0) {
    Write-Error "pg_isready reported the server is not accepting connections (exit code $LASTEXITCODE)."
    exit 1
}

Write-Host "Server is accepting connections. Fetching connection info..."
psql -X -q -c '\conninfo'
