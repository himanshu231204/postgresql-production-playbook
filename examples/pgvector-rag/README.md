# pgvector RAG Example

Minimal end-to-end retrieval pipeline: chunk documents, embed, store in
PostgreSQL with pgvector, search by cosine distance, assemble an LLM prompt.
Design explanation: [10-pgvector/rag-example.md](../../10-pgvector/rag-example.md).

**Stub embedder.** `app/embeddings.py` ships a deterministic hashed
bag-of-words `StubEmbedder` so the example runs offline with no API key. It is
**not a semantic model**: it only matches shared words, and its results say
nothing about real retrieval quality. To use a real model, implement the
`Embedder` interface in that file and return it from `get_embedder()`. The
model's output dimension **must equal** `vector(384)` in `schema.sql` and
`EMBEDDING_DIM`; the app checks this at startup and refuses to run on a
mismatch. Changing models means re-embedding every stored row.

The example builds the prompt but does not call an LLM.

## Validated against

PostgreSQL 16, pgvector extension 0.8.1, Python 3.13, SQLAlchemy 2.1.3,
asyncpg 0.31.0, `pgvector` (Python) 0.5.0. The HNSW index requires pgvector
0.5.0 or later. The app was run end-to-end (ingest twice, search, filtered
search, `--explain`, dimension-mismatch guard).

## Layout

| Path | Purpose |
|---|---|
| `schema.sql` | Extension, tables, HNSW index (run once as an admin/migration role) |
| `app/config.py` | Environment-based settings |
| `app/embeddings.py` | `Embedder` interface + stub |
| `app/chunking.py` | Fixed-size chunking with overlap |
| `app/models.py` | SQLAlchemy 2.x `Mapped[...]` models (mirror `schema.sql`) |
| `app/db.py` | Async engine/session factory, dimension guard |
| `app/ingest.py` | Idempotent ingestion |
| `app/retrieval.py` | Cosine search, optional category filter, prompt builder |
| `app/cli.py` | `ingest` and `ask` commands |
| `sample_docs/` | Four short sample documents |
| `.env.example` | Placeholder configuration |

## Setup

Prerequisite: PostgreSQL with pgvector installed on the server; see
[10-pgvector/installation.md](../../10-pgvector/installation.md).

1. Create a database and apply the schema (Unix shell; `psql` as a role
   allowed to `CREATE EXTENSION`):

   ```bash
   createdb -h localhost -U postgres ragdemo
   psql -h localhost -U postgres -d ragdemo -f schema.sql
   ```

2. Create a virtual environment **outside** the repository and install:

   ```bash
   python3 -m venv ~/venvs/pgvector-rag
   ~/venvs/pgvector-rag/bin/pip install -r requirements.txt
   ```

3. Configure (the `.env` file is git-ignored; never commit it):

   ```bash
   cp .env.example .env
   # edit DATABASE_URL: postgresql+asyncpg://USER:PASSWORD@HOST:5432/DATABASE
   ```

   Application role: use a role with only `SELECT, INSERT, UPDATE, DELETE` on
   `documents` and `chunks`, not a superuser
   ([06-security/least-privilege.md](../../06-security/least-privilege.md)).

## Run

Run from this directory:

```bash
~/venvs/pgvector-rag/bin/python -m app.cli ingest
~/venvs/pgvector-rag/bin/python -m app.cli ask "how do I stop dead tuples and bloat"
~/venvs/pgvector-rag/bin/python -m app.cli ask "least privilege for the app role" --category security
~/venvs/pgvector-rag/bin/python -m app.cli ask "backup restore" --explain
```

Expected result: `ingest` prints `ingested <file>: 1 chunks` per sample
document and can be re-run without duplicating rows. `ask` prints top-k hits
as `cosine_distance  source#chunk  text...` (the `vacuum.md` chunk ranks first for
the first query), followed by the assembled prompt. `--explain` prints the plan;
confirm it shows an `Index Scan using chunks_embedding_hnsw` (on a tiny table the
planner can also choose a sequential scan, which is correct behavior).

## Notes and limitations

- Distance metric: cosine (`<=>`) with `vector_cosine_ops`; see
  [similarity-search.md](../../10-pgvector/similarity-search.md).
- With an approximate index, the category filter is applied after the index
  scan and may return fewer than `TOP_K` rows
  ([indexing.md](../../10-pgvector/indexing.md#iterative-index-scans-pgvector-080)).
- Fixed-size character chunking is a simplification; chunking strategy
  materially affects retrieval quality.
- Sample documents are tiny, so each yields one chunk; use your own corpus to see chunking.
- Re-ingest replaces a source's chunks inside one transaction. Deleting a
  document cascades to its chunks (`ON DELETE CASCADE`); back up before bulk deletes.
- No tests are included; validation was a manual end-to-end run.
