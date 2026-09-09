# Contributing

This repository is a production reference, not a tutorial series. Content
quality and accuracy matter more than coverage. Before contributing, read
[AGENTS.md](AGENTS.md) — it is the full operating manual (structure,
documentation format, security rules, validation requirements) and applies
to human and AI contributors alike.

## Before you start

1. Check whether a page already covers your topic. Update it rather than
   creating a duplicate.
2. Confirm which numbered section your content belongs in (see the table in
   [README.md](README.md)). Don't create a new top-level folder unless the
   topic genuinely doesn't fit an existing one.
3. If you're filling in a scaffold page (`> Status: scaffold` at the top),
   remove that line once the page has real content.

## Content requirements

- **Accuracy first.** Verify PostgreSQL syntax, configuration parameters,
  and library APIs (SQLAlchemy, Alembic, FastAPI, pgvector) against
  official documentation before writing them down. Do not write from
  memory when precision matters.
- **State version assumptions.** If behavior depends on a PostgreSQL or
  library version, say so explicitly.
- **No secrets.** Never commit real passwords, API keys, cloud
  credentials, or connection strings. Use `.env.example` files and
  placeholders.
- **Explain tradeoffs.** Don't present one approach as universally
  correct — call out the alternative and when it would win instead.
- **Flag destructive operations.** Any `DROP`, `TRUNCATE`, `VACUUM FULL`,
  `pg_terminate_backend`, or destructive migration must state what it does,
  why it's risky, and a safer alternative where one exists.

## Page format

Most topic pages should follow:

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

Skip sections that don't apply — a short command-reference page doesn't
need "AI/agentic use case." See AGENTS.md §4–5 for full detail, including
command-table formatting and how to correctly label PowerShell vs. Unix
shell vs. SQL vs. psql meta-commands.

## Code contributions

Python examples use type hints, SQLAlchemy 2.x APIs, and async patterns
where the surrounding code is async. See AGENTS.md §6 for the full standard.

## Validation before submitting

- Markdown: headings render, code fences are closed and language-tagged,
  internal links resolve, tables are well-formed.
- SQL: syntax is valid for the PostgreSQL version stated.
- Python: formatted, linted, and any tests pass.
- Docker: compose/Dockerfile syntax validates.

Don't claim a check was run if it wasn't. State any known limitations in
your PR description.

## Pull requests

Keep PRs focused — one topic or one coherent set of related pages per PR.
Describe what changed and what validation you performed.
