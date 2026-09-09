# Production PostgreSQL Reference for AI & Backend Engineers

A practical reference for running PostgreSQL locally, in Docker, and in
cloud production environments — built for engineers who need the correct
command, syntax, and production tradeoff *now*, not a beginner tutorial to
read cover to cover.

This is not "learn SQL." It's the repository you open mid-code-review,
mid-incident, or mid-interview-prep to find: the exact syntax, the
Windows/macOS/Linux equivalent, why it matters in production, what mistakes
to avoid, and how it applies to AI/agentic systems built on PostgreSQL.

See [AGENTS.md](AGENTS.md) for the conventions this repository follows and
the rules AI coding agents must respect when contributing to it.

## Learning path

```
CLI → SQL → Database Design → Transactions → Performance → Security →
Backups → FastAPI → SQLAlchemy → Alembic → pgvector → Agentic AI →
Docker → Cloud → Observability → Production Runbooks
```

Each stage builds on the last: you need working SQL before performance
tuning means anything; you need transactions and locking before
production migrations are safe; you need a solid relational schema before
pgvector and agentic-AI state design make sense.

## Table of contents

| # | Section | Covers |
|---|---|---|
| 01 | [PostgreSQL CLI](01-postgresql-cli/) | `psql`, service management, connecting |
| 02 | [SQL Fundamentals](02-sql-fundamentals/) | SELECT, joins, aggregations, CTEs, window functions |
| 03 | [Database Design](03-database-design/) | Keys, constraints, normalization, indexing, naming |
| 04 | [Transactions](04-transactions/) | ACID, isolation levels, locking, deadlocks |
| 05 | [Performance](05-performance/) | EXPLAIN/ANALYZE, indexing, VACUUM, pooling |
| 06 | [Security](06-security/) | Roles, least privilege, secrets, TLS |
| 07 | [Backups & Recovery](07-backups-recovery/) | pg_dump/pg_restore, PITR, disaster recovery |
| 08 | [Python + FastAPI](08-python-fastapi/) | SQLAlchemy 2.x, async PostgreSQL, pooling |
| 09 | [Alembic](09-alembic/) | Migrations, production migration safety, rollback |
| 10 | [pgvector](10-pgvector/) | Embeddings, similarity search, indexing, RAG |
| 11 | [Agentic AI](11-agentic-ai/) | PostgreSQL as persistent state for AI agents |
| 12 | [Docker](12-docker/) | Dockerfile, compose, volumes, dev vs. prod |
| 13 | [Cloud Production](13-cloud-production/) | Managed PostgreSQL, networking, HA, scaling |
| 14 | [Observability](14-observability/) | Diagnostic queries, metrics, monitoring |
| 15 | [Production Runbooks](15-production-runbooks/) | Incident response playbooks |
| 16 | [Command Reference](16-command-reference/) | OS- and tool-specific command tables |

Additional top-level references:

- [QUICKSTART.md](QUICKSTART.md) — fastest path to a working local PostgreSQL setup
- [CHEATSHEET.md](CHEATSHEET.md) — compact, fast-scan command tables
- [CONTRIBUTING.md](CONTRIBUTING.md) — how to add or update content
- [examples/](examples/) — complete, runnable example projects
- [scripts/](scripts/) — health-check, backup, restore, and diagnostic scripts

## Who this is for

- Engineers learning PostgreSQL specifically for production use
- Engineers revising PostgreSQL before an interview
- Backend engineers deploying APIs against PostgreSQL
- AI engineers building RAG or agentic applications on pgvector
- Production/platform engineers operating cloud PostgreSQL
- Anyone troubleshooting PostgreSQL in production, under time pressure

## How to use this repo

1. **Learning it for the first time?** Start at `01-postgresql-cli/` and
   move through the numbered sections in order.
2. **Revising before an interview or a deploy?** Go straight to
   `CHEATSHEET.md` or the relevant numbered section's own quick-revision
   notes.
3. **Troubleshooting a live incident?** Go straight to
   `15-production-runbooks/` for the matching symptom.
4. **Building an AI/agentic backend?** Follow `08-python-fastapi/` →
   `09-alembic/` → `10-pgvector/` → `11-agentic-ai/` in order — that's the
   stack progression this repo is built around.
5. **Need a command right now?** Check `16-command-reference/` or
   `CHEATSHEET.md` first; they're built for scanning, not reading.

## Production mindset

This repository treats every example as something that could run against a
real, live database with real traffic and real data. That means:

- Tradeoffs are explained, not hidden — there is rarely one universally
  correct answer (sync vs. async, index choices, HNSW vs. IVFFlat, cloud
  vs. self-hosted).
- Destructive operations (`DROP TABLE`, `TRUNCATE`, `VACUUM FULL`,
  `pg_terminate_backend`, destructive migrations) are always flagged with
  why they're risky and what to do instead.
- Security is never an afterthought: no real secrets appear anywhere in
  this repo, and least-privilege role separation is the default guidance.
- Version assumptions are stated explicitly wherever behavior depends on
  them.

## Status

This repository is under active construction. The directory structure and
navigation are in place; individual pages are being filled in incrementally.
A page marked `> Status: scaffold` has not been written yet — see
[CONTRIBUTING.md](CONTRIBUTING.md) if you'd like to help complete one.

## License

See [LICENSE](LICENSE).
