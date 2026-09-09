# AGENTS.md

Operating manual for AI coding agents (Claude Code, Codex, Cursor, GitHub
Copilot agents, and similar) working in this repository. Read this file
before making changes.

## 1. What this repository is

**Production PostgreSQL Reference for AI, Backend & Production Engineers.**

This is a practical, production-grade reference and revision guide covering
the full stack an engineer touches when running PostgreSQL in real systems:

```
PostgreSQL CLI → SQL → Database Design → Transactions → Performance →
Security → Backup & Recovery → FastAPI → SQLAlchemy → Alembic →
pgvector → Agentic AI → Docker → Cloud PostgreSQL → Observability →
Production Runbooks
```

It is **not** a beginner SQL tutorial and not a general programming
cookbook. It exists so an engineer can open it during real work and find:
the exact command, correct syntax, OS-specific variant, production
considerations, common mistakes, security implications, performance
implications, and (where relevant) how it applies to AI/agentic systems.

### Who it's for

- Engineers learning PostgreSQL for production use
- Engineers revising PostgreSQL before an interview
- Backend engineers deploying APIs against PostgreSQL
- AI engineers building RAG/agentic applications on pgvector
- Production/platform engineers operating cloud PostgreSQL
- Anyone troubleshooting PostgreSQL in production, under time pressure

### Priority order

**Production correctness over quantity of content.** A repo with fewer,
verified, precise pages is more valuable than one with many pages of
plausible-sounding but unverified content. Never trade accuracy for
coverage.

## 2. Core principles (non-negotiable)

1. **Accuracy first.** Never write PostgreSQL syntax, flags, configuration
   parameters, or version-specific behavior from memory when correctness
   matters and you are unsure. Verify against official documentation
   (PostgreSQL, SQLAlchemy, Alembic, FastAPI, pgvector, asyncpg, Docker).
   Do not invent commands, parameters, or cloud features.
2. **Production first.** Examples should look like something you'd actually
   run against a production system, not a toy script. Skip toy patterns
   when a production-safe pattern can be shown instead.
3. **Security first.** Never commit real passwords, API keys, cloud
   credentials, private keys, or production connection strings. Use
   environment variables and clearly fake placeholders.
4. **Explicit versioning.** When behavior depends on a PostgreSQL version
   or a library version (SQLAlchemy 1.x vs 2.x, Alembic, pgvector), state
   the version explicitly.
5. **Explain tradeoffs, don't declare winners.** Sync vs async, pooling
   strategies, HNSW vs IVFFlat, read replicas, index choices, migrations,
   cloud vs self-hosted — present the tradeoff, not a single "correct"
   answer.

## 3. Repository structure

Preserve this structure unless there is a strong, stated reason to change
it. If a new topic doesn't fit an existing folder, prefer adding a page to
the closest existing folder over creating a new top-level folder.

| Path | Responsibility |
|---|---|
| `README.md` | Entry point: what this repo is, learning path, table of contents |
| `QUICKSTART.md` | Fastest path to a working local PostgreSQL setup |
| `CHEATSHEET.md` | Compact, fast-scan command tables across all topics |
| `CONTRIBUTING.md` | How to propose/add content |
| `01-postgresql-cli/` | `psql`, service management, connection basics |
| `02-sql-fundamentals/` | SELECT, INSERT/UPDATE/DELETE, JOINs, aggregations, CTEs, subqueries, window functions |
| `03-database-design/` | Schemas, keys, constraints, normalization, indexes, naming conventions |
| `04-transactions/` | Transactions, ACID, isolation levels, locking, deadlocks |
| `05-performance/` | EXPLAIN/ANALYZE, query optimization, indexing, VACUUM, pooling |
| `06-security/` | Roles, permissions, least privilege, secrets, SSL/TLS |
| `07-backups-recovery/` | pg_dump/pg_restore, backup strategy, PITR, disaster recovery |
| `08-python-fastapi/` | FastAPI + SQLAlchemy 2.x + asyncpg production patterns |
| `09-alembic/` | Migration workflow, production migration safety, rollback |
| `10-pgvector/` | Vector columns, embeddings, similarity search, indexing, RAG |
| `11-agentic-ai/` | PostgreSQL as persistent state for AI agents/LLM systems |
| `12-docker/` | Dockerfile, compose, volumes, env vars, dev-vs-prod separation |
| `13-cloud-production/` | Vendor-neutral managed PostgreSQL architecture + provider notes |
| `14-observability/` | Diagnostic queries, metrics, monitoring |
| `15-production-runbooks/` | Incident runbooks (symptoms → diagnosis → remediation) |
| `16-command-reference/` | OS-specific and tool-specific command tables |
| `examples/` | Complete, runnable example projects |
| `scripts/` | Health-check, backup, restore, diagnostic scripts |

Numeric prefixes encode the intended learning/reference order. Do not
renumber existing folders to insert a new one; append a new topic to the
closest existing folder, or discuss renumbering explicitly if a new
top-level section is truly warranted.

## 4. Documentation page format

Prefer this section order for a substantial topic page:

```
# Topic
## What it is
## Why it matters
## Syntax
## Example
## Production usage
## Common mistakes
## Security considerations
## Performance considerations
## AI/agentic use case
## Troubleshooting
## Quick revision
```

Do not force every section onto every page — a short reference page (e.g.
one command table) doesn't need "AI/agentic use case." Use judgment: include
a section only when it adds real content.

Documentation should be:

- Concise and scannable, not narrative
- Command-oriented and example-driven
- Cross-linked to related pages (e.g. an indexing page links to
  `05-performance/explain.md`, `08-python-fastapi/`, and
  `10-pgvector/indexing.md` where relevant)
- Written as direct instructions ("Run `VACUUM ANALYZE table;`"), not hedged
  suggestions ("you might want to consider...")

## 5. Command documentation rules

Every command entry must cover: command name, platform, syntax, purpose,
example, expected result, and production considerations.

Use this table format for command references:

```
| Command | Windows | macOS | Linux | Purpose | Production Notes |
```

Strictly distinguish command types — never mislabel one as another:

- **PowerShell** (Windows): `Get-Service`, `Start-Service`, `Test-NetConnection`
- **Windows CMD**: distinct from PowerShell where syntax differs
- **Unix shell** (macOS/Linux): `brew services`, `systemctl`, `journalctl`, `ss`, `ps`
- **PostgreSQL SQL**: `CREATE TABLE`, `EXPLAIN ANALYZE`, `VACUUM`, etc.
- **psql meta-commands**: `\l`, `\c`, `\dt`, `\d`, `\d+`, `\dn`, `\du`, `\dx`,
  `\conninfo`, `\timing`, `\x`, `\q` — these are **psql client commands**,
  never SQL and never OS commands. Do not present `\dt` as SQL syntax.
- **Docker commands**: `docker run`, `docker compose`

When adding a new command anywhere in the repo, explain: what it is, which
platform/tool it belongs to, syntax, purpose, a runnable example, the
expected result, and any production caveat (locking, blocking, destructive
potential, permissions required).

## 6. Code standards

**Python** (used in `08-python-fastapi/`, `09-alembic/`, `10-pgvector/`,
`11-agentic-ai/`, `examples/`, `scripts/`):

- Type hints on all function signatures
- Clear, realistic names — no `foo`/`bar`/`data1`
- Small, single-purpose functions
- Explicit error handling (no bare `except:`)
- Configuration via environment variables, never hardcoded
- Dependency injection for DB sessions (FastAPI `Depends`)
- Async patterns where the stack is async (asyncpg + async SQLAlchemy)
- **SQLAlchemy 2.x style only**: `select()`, `Session`/`AsyncSession`,
  `Mapped[...]`/`mapped_column()` declarative models. Do not use legacy
  `Query`-only patterns or 1.x-style imperative mapping in new examples.

**FastAPI**: modern patterns — `Annotated` dependencies, Pydantic v2 models,
lifespan context managers for startup/shutdown (not deprecated
`@app.on_event`).

**Alembic**: use the standard `alembic revision`/`upgrade`/`downgrade`
workflow; never hand-edit a migration file that has already been applied in
a real environment without explicitly calling out the risk and scenario.

**SQL**: parameterized queries only. Never string-format user input into a
query, in examples or in `scripts/`.

## 7. Security rules

Never commit:

- `.env` files, credentials, private keys, API tokens
- Cloud provider credentials
- Real database passwords or production connection strings

Instead:

- Provide `.env.example` files with placeholders, e.g.
  `DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:5432/DATABASE`
- Document least privilege: separate **application role** (CRUD only),
  **migration role** (DDL), and **administrator role** (full control) where
  a topic touches roles/permissions
- Show BAD vs GOOD examples for security-sensitive topics (SQL injection,
  hardcoded secrets, overly broad grants)

If you ever notice a real-looking secret in a diff you're about to commit,
stop and flag it — do not commit it "to fix later."

## 8. Database design rules

Default to:

- Explicit primary keys
- Foreign keys with an explicit `ON DELETE`/`ON UPDATE` policy
- `NOT NULL` where the domain requires it
- `UNIQUE` and `CHECK` constraints to enforce invariants in the database,
  not only in application code
- Appropriate types (e.g. `TIMESTAMPTZ` over `TIMESTAMP` for anything
  crossing time zones or services)
- Indexes justified by an actual query pattern

Never add an index "just in case." Every index recommendation must state
what query it serves and the tradeoff: faster reads for that query pattern
vs. extra storage and slower writes (every INSERT/UPDATE maintains every
index on the row).

## 9. Performance rules

Never write "add an index and it will be faster" as a complete answer.
Ground performance guidance in mechanism:

- `EXPLAIN` / `EXPLAIN ANALYZE` output and how to read it
- Query planning and planner statistics (`ANALYZE`)
- Index selectivity, not just index existence
- Connection pooling behavior
- VACUUM / autovacuum and table bloat
- Query shape (N+1 detection, pagination strategy — keyset vs offset)

Do not state universal numeric thresholds (e.g. "anything over 100ms is
slow") unless sourced from official documentation or explicitly labeled as
an illustrative example, not a production rule.

## 10. Migration rules

Treat every production migration example as a high-risk operation. When
writing about migrations, address:

- Backward compatibility (can the old and new app versions both run against
  the mid-migration schema?)
- Locking behavior on the affected table
- Large-table migration strategy (batching, `CONCURRENTLY` where
  applicable)
- Deployment ordering (migrate-then-deploy vs deploy-then-migrate)
- Rollback strategy

Never casually recommend a destructive migration (dropping a column,
renaming in place, etc.) as a first option. Never instruct hand-editing an
already-applied migration file unless the scenario explicitly requires it
and the consequences (drift between migration history and actual schema)
are explained.

## 11. pgvector rules

For every pgvector example, be explicit about:

- Embedding dimension (and that it must match the model that produced it)
- Distance metric used (cosine, L2, inner product) and why
- Index type chosen (HNSW vs IVFFlat) and the tradeoff (build time/memory
  vs query recall/speed)
- Metadata filtering approach
- That retrieval quality depends on chunking/embedding strategy, not just
  the index

Do not imply PostgreSQL + pgvector is universally superior to a dedicated
vector database. State when a dedicated vector DB may make more sense
(very large scale, specialized ANN requirements) and when pgvector's
advantage (single system, transactional consistency with relational data)
dominates.

## 12. Agentic AI database rules

When documenting or building schemas for AI/agent systems in
`11-agentic-ai/` or `examples/`, model around these entities where relevant:
`users`, `conversations`, `messages`, `agent_runs`, `tool_calls`,
`workflow_state`, `tasks`, `audit_logs`, `model_usage`, `evaluation_runs`.

Design for production concerns, not just "it works once":

- Idempotency (a retried tool call or agent step must not double-apply)
- Retries and resumability (workflow/task state must be reconstructable)
- Auditability (who/what/when for every state change)
- Concurrency (two workers must not corrupt shared agent state)
- Transactional consistency between agent state and business data

**Never treat an LLM's output as trusted database input.** Validate and
constrain anything an LLM produces (tool arguments, generated SQL, free-text
that becomes structured data) before it reaches a write path, exactly as you
would validate any other untrusted external input.

## 13. Docker rules

- Configuration via environment variables, not hardcoded values
- Persistent named volumes for local PostgreSQL data
- Health checks (`pg_isready` or equivalent) where they add value
- Clearly separate a local development compose setup from any
  production-deployment guidance — they are not the same thing
- Never put real production secrets in a `Dockerfile` or
  `docker-compose.yml`; use `.env` files (git-ignored) or a secrets manager,
  and show `.env.example` in the repo instead

## 14. Cloud rules

Keep core concepts cloud-neutral: private networking, firewall/security
groups, TLS, secrets management, backups, HA/failover, monitoring, scaling,
connection limits.

When adding provider-specific content (AWS RDS/Aurora, Azure Database for
PostgreSQL, GCP Cloud SQL/AlloyDB, etc.):

- Clearly label it as provider-specific, separate from the vendor-neutral
  concept explanation
- Do not assert a provider feature exists without verifying it against
  that provider's current documentation

## 15. Source of truth

Before writing or changing version-sensitive technical content, prefer
official documentation:

- PostgreSQL: https://www.postgresql.org/docs/
- SQLAlchemy: https://docs.sqlalchemy.org/
- Alembic: https://alembic.sqlalchemy.org/
- FastAPI: https://fastapi.tiangolo.com/
- pgvector: https://github.com/pgvector/pgvector
- Docker: https://docs.docker.com/

Use the Context7 documentation lookup (or a web search/fetch tool) to check
current library docs when a task is version-sensitive — do not rely on
memory for details that have a real chance of having changed. Do not invent
commands, configuration parameters, or provider features.

## 16. Change workflow

Before editing:

1. Inspect the target directory and any related directories.
2. Read the existing page(s) fully to understand local conventions and
   avoid duplicating existing content.
3. Identify pages that should cross-link to (or from) the change.
4. Make the smallest coherent change that fully addresses the request.
5. Update cross-links affected by the change.
6. Validate examples (see Section 17) before considering the change done.

Do not rewrite unrelated files. Do not create a new page duplicating an
existing one — update the existing page instead.

## 17. Validation before committing

- **Markdown**: headings render correctly, code fences are closed and
  tagged with a language, tables are aligned and parse, internal links
  resolve to real files/anchors.
- **SQL**: syntax is valid for the PostgreSQL version stated; check
  assumptions (does the referenced table/column/extension exist in the
  example's own context); test against the stated version where a database
  is available in the environment.
- **Python**: format and lint (repo's configured tools, e.g. `ruff`/`black`
  if present), run any test suite provided, verify imports resolve.
- **Docker**: `docker compose config` (or equivalent) to validate compose
  file syntax; confirm `Dockerfile` builds if changed.
- **Examples**: required environment variables are documented (in
  `.env.example` or the page itself); setup steps are complete enough to
  actually run.

Never state that tests, linting, or documentation verification were
performed if they were not actually run.

## 18. Production safety in content

Explicitly flag destructive commands wherever they appear: `DROP DATABASE`,
`DROP TABLE`, `DELETE` (without WHERE or at scale), `TRUNCATE`, `VACUUM
FULL` (takes an exclusive lock), `pg_terminate_backend`, and any destructive
migration.

For each, when it appears in an example or runbook, note: what it does, why
it's risky in production, a safer alternative where one exists, and the
precaution to take before running it (backup, maintenance window,
confirming the target). Never present a destructive command as a casual or
default first option for a production database.

## 19. Writing style

- Direct, professional engineering tone: "Run `ALTER TABLE ... ADD COLUMN
  ... ;`" not "You might want to consider adding a column."
- No motivational filler.
- Prefer Mermaid diagrams for architecture (agent pipelines, cloud topology,
  data flow). Artifacts render Mermaid natively in fenced ```mermaid blocks.

## 20. Agent workflow for a task in this repo

1. Understand exactly what change is being requested.
2. Inspect the relevant existing files (Section 16).
3. Make a focused change consistent with Sections 2–15.
4. Validate the change (Section 17).
5. Summarize: files changed, what changed, validation actually performed,
   and any known limitations or unverified assumptions.

Do not claim verification steps happened if they didn't.

## 21. Definition of done

A change is complete only when:

- The content/implementation is technically correct
- It follows the applicable format and section conventions
- Examples are internally consistent (same variable names, same schema,
  runnable together)
- No secrets were introduced
- Cross-links added or referenced actually resolve
- Version assumptions are stated where behavior is version-dependent
- Validation (Section 17) was actually performed, and the summary says so
  honestly

## 22. Repository philosophy

This repository is meant to be opened repeatedly during real engineering
work — treat every page as something someone will land on mid-incident or
mid-code-review, not read cover to cover. Optimize for:

**Find → Understand → Copy → Adapt → Validate**

not for exhaustive, tutorial-style reading. When in doubt between adding
more explanation and keeping a page scannable, keep it scannable and link
to the deeper page instead.
