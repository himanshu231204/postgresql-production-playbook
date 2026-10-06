# pgvector Installation

## What it is

Installing the pgvector shared library on the **database server**, then
enabling it per database with `CREATE EXTENSION vector`. The package name is
`pgvector`; the extension name is `vector`.

## Why it matters

The extension must match your PostgreSQL major version, and must be enabled
in every database that uses it. A client-side `pip install pgvector` does not
install the server extension.

## Install on the server

| Platform | Command (Unix shell unless noted) | Notes |
|---|---|---|
| Debian/Ubuntu (PGDG APT repo) | `sudo apt install postgresql-16-pgvector` | Replace `16` with your major version. Package version depends on your repo; check after install. Package may be missing from distro default repos; add the PostgreSQL APT repository |
| RHEL/Fedora (PGDG Yum repo) | `sudo yum install pgvector_16` | Replace `16`; confirm the package name for your repo |
| macOS (Homebrew) | `brew install pgvector` | Adds the extension only to specific Homebrew `postgresql@N` formulas (see the pgvector README for which); verify it matches the server you run |
| Docker | `docker pull pgvector/pgvector:pg16` | Official PostgreSQL image with pgvector added; run it like `postgres` |
| Source (Linux/macOS) | `git clone --branch v0.8.1 https://github.com/pgvector/pgvector.git && cd pgvector && make && sudo make install` | Needs PostgreSQL server dev headers (`postgresql-server-dev-16`). Use `make PG_CONFIG=/path/to/pg_config` when several versions are installed |
| Windows (CMD, VS x64 Native Tools prompt as administrator) | `set "PGROOT=C:\Program Files\PostgreSQL\16"` then `nmake /F Makefile.win` and `nmake /F Makefile.win install` | Run from a clone of the pgvector repo; needs Visual Studio C++ tools |

Package names and versions change; confirm against the
[pgvector README](https://github.com/pgvector/pgvector#installation) for your
platform.

## Enable in a database

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

Run once **per database**. This is SQL, run through `psql` or a migration.

```sql
SELECT extversion FROM pg_extension WHERE extname = 'vector';
```

Expected result: one row, e.g. `0.8.1`. To see what the server could install:

```sql
SELECT name, default_version, installed_version
FROM pg_available_extensions WHERE name = 'vector';
```

If the row is missing, the shared library is not installed for this server's
major version (install step above, then retry; no restart is needed for
`CREATE EXTENSION`).

## Docker Compose (local development only)

```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 5s
      retries: 10
volumes:
  pgdata:
```

Values come from a git-ignored `.env`. Production deployment is a different
concern; see [12-docker/](../12-docker/README.md). The image ships the
extension files; you still run `CREATE EXTENSION`.

## Upgrading pgvector

1. Install the new package/build using the same method as the original install.
2. In **each** database that uses it:

```sql
ALTER EXTENSION vector UPDATE;
```

3. Verify with the `extversion` query above.

Upgrade in staging first. Index and planner behavior can change between releases, so
re-run `EXPLAIN` on your key queries and re-measure recall. Upgrading PostgreSQL itself (major
version) requires the extension installed for the new version before
`pg_upgrade`.

## Production usage

- Put `CREATE EXTENSION` in a migration run by the **migration/admin role**,
  not by the application role. See
  [06-security/least-privilege.md](../06-security/least-privilege.md). In the
  validated build (0.8.1) the extension is **not** marked trusted
  (`SELECT trusted FROM pg_available_extension_versions WHERE name = 'vector';`
  returned `f`), so creating it needs a superuser or a provider-granted
  equivalent. Check your own install rather than assuming.
- Alembic: `op.execute("CREATE EXTENSION IF NOT EXISTS vector")` in an early
  revision; see [09-alembic/production-migrations.md](../09-alembic/production-migrations.md).
- Restores: `pg_dump` output references the extension; the target server needs
  the same (or compatible) pgvector installed before `pg_restore`. See
  [07-backups-recovery/pg-restore.md](../07-backups-recovery/pg-restore.md).

## Managed PostgreSQL

Many managed services offer pgvector, but availability, the installed
version, and which features (for example iterative scans, from 0.8.0) you get
differ by provider and change over time. Check your provider's current
documentation and run the `extversion` query above; do not assume. See
[13-cloud-production/managed-postgresql.md](../13-cloud-production/managed-postgresql.md).

## Common mistakes

- Installing the Python `pgvector` package and expecting `CREATE EXTENSION` to work.
- Installing the extension for a different PostgreSQL major version than the running server.
- Enabling it in `postgres` but not in the application database.
- Forgetting `ALTER EXTENSION vector UPDATE` after upgrading the binaries, so the database keeps the old SQL objects.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `could not open extension control file ".../vector.control"` | Extension not installed for this server version. Install the matching package/build |
| `extension "vector" is not available` | Same as above |
| `permission denied to create extension "vector"` | Role lacks the privilege; run as admin/migration role |
| `type "vector" does not exist` | Extension not enabled in the connected database, or `search_path` excludes its schema |
| `SET hnsw.iterative_scan` fails or has no effect | pgvector older than 0.8.0 (the setting was added in 0.8.0); check `extversion` |

## Quick revision

- Server install, then `CREATE EXTENSION vector;` per database.
- Verify with `extversion`; upgrade with `ALTER EXTENSION vector UPDATE;`.
- Do not assume provider version or feature availability.
