# Dockerfile

Two cases: building an application image that talks to PostgreSQL, and
extending the official `postgres` image. Reference file:
[examples/Dockerfile](examples/Dockerfile). Applies to the stack in
[08-python-fastapi/](../08-python-fastapi/).

## Multi-stage Python application image

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.12-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
COPY requirements.txt .
RUN pip install -r requirements.txt

FROM python:3.12-slim AS runtime
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN groupadd --system --gid 10001 app \
 && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY --chown=app:app app/ ./app/
USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

| Choice | Reason |
|---|---|
| Builder stage with a venv, copied to runtime | Compilers and build caches do not ship in the final image |
| `requirements.txt` copied before source | Dependency layer is cached until the manifest changes |
| Non-root `USER app` | A compromised process does not run as root |
| No `ENV`/`ARG` for credentials | Values persist in image layers and `docker history`; inject `DATABASE_URL` at runtime |
| Pinned base image tag | Reproducible builds; update deliberately. The `3.12` tag is an example; use the version you test against |

Pin dependencies in `requirements.txt` (including SQLAlchemy 2.x and the
async driver, e.g. `asyncpg`), and use a lock file or hashes where your
workflow supports it.

## `.dockerignore`

Keep secrets and noise out of the build context
([examples/.dockerignore](examples/.dockerignore)):

```text
.git
.env
.env.*
secrets/
**/__pycache__/
.venv/
```

`COPY . .` without a `.dockerignore` copies `.env` into the image layer.

## BAD vs GOOD: secrets

```dockerfile
# BAD: persists in image layers and metadata
ENV DATABASE_URL=postgresql://USER:real-password@db/appdb
ARG DB_PASSWORD
```

```bash
# GOOD: provided at runtime (Unix shell); value comes from the environment or a secrets manager
docker run --rm --env-file .env my-api:1.0
```

Build-time secrets (e.g. a private package index token) use BuildKit
`RUN --mount=type=secret`, which is not stored in layers. See
[environment-variables.md](environment-variables.md).

## Migrations and startup

Do not run Alembic migrations in the default `CMD` of every replica: N
containers race to migrate. Run migrations as a separate one-off step
(`docker compose run --rm app alembic upgrade head`) before rolling the app,
using the migration role. See [09-alembic/](../09-alembic/).

## Extending the `postgres` image

Only extend it to add extensions or init scripts:

```dockerfile
FROM postgres:16
COPY initdb/ /docker-entrypoint-initdb.d/
```

- Scripts (`*.sql`, `*.sql.gz`, `*.sh`) run in sorted order, **only when the
  data directory is empty**. They do not re-run on an existing volume.
- A failing script aborts the entrypoint; a restart on the partially
  initialized volume will not resume it.
- For `.sh` scripts, run `psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB"`.
- Schema changes belong in migrations, not init scripts.
- Extensions such as pgvector need an image that ships them (or a custom
  build). Verify the package/version against the pgvector README:
  [10-pgvector/](../10-pgvector/).

## Validation

```bash
# Unix shell
docker build -t my-api:dev -f 12-docker/examples/Dockerfile <context-with-requirements.txt-and-app/>
docker run --rm my-api:dev id
```

Expected: `uid=10001(app)`. The example Dockerfile requires `requirements.txt`
and an `app/` package in the build context.

## Common mistakes

- Running as root; copying `.env` into the image; `latest` tags.
- `pip install` before copying only the manifest, defeating layer caching.
- Baking a connection string into the image.
- Using `0.0.0.0` binding without limiting published ports at the Compose layer.

## Quick revision

- Multi-stage, non-root, `.dockerignore`, no secrets in layers.
- Init scripts run once, on an empty data directory.
- Migrate as a separate step, not in every replica's `CMD`.
