# pgvector

## What it is

`pgvector` is a PostgreSQL extension (extension name `vector`) that adds
vector column types, distance operators, and approximate-nearest-neighbor
indexes (HNSW, IVFFlat). It lets you store embeddings next to relational
data and query them with SQL.

## Why it matters

RAG and semantic search need "find the rows whose embeddings are closest to
this query embedding." With pgvector that lookup lives in the same database
as your users, permissions, and transactions, so a row and its embedding
commit or roll back together and `WHERE` filters, joins, and backups work as
they already do.

## In this section

| Page | Covers |
|---|---|
| [installation.md](installation.md) | Install per OS/Docker, `CREATE EXTENSION vector`, version check, upgrades, managed services |
| [embeddings.md](embeddings.md) | Column types, dimensions, storage, normalization, model/dimension coupling, re-embedding |
| [similarity-search.md](similarity-search.md) | Distance operators, choosing a metric, exact vs. approximate, metadata filtering, EXPLAIN |
| [indexing.md](indexing.md) | HNSW vs. IVFFlat, parameters, build memory, `CONCURRENTLY`, iterative scans, partial indexes/partitioning |
| [rag-example.md](rag-example.md) | RAG pipeline design: schema, chunking, ingestion, retrieval, prompt assembly, failure modes |
| [examples/pgvector-rag/](../examples/pgvector-rag/README.md) | Runnable example (SQLAlchemy 2.x async, no API key needed) |

## Version notes

SQL and the example were validated on **PostgreSQL 16** with **pgvector
0.8.1** (built from source; the Debian/Ubuntu `postgresql-16-pgvector` package
available in the validation environment was 0.6.0). Version-dependent
features are labeled where they appear:

| Feature | pgvector version |
|---|---|
| `vector`, IVFFlat | 0.1.0 and later |
| HNSW index | 0.5.0 |
| `halfvec`, `sparsevec`, `bit` indexing, `<+>` (L1) | 0.7.0 |
| Iterative index scans (`hnsw.iterative_scan`, `ivfflat.iterative_scan`) | 0.8.0 |

Check the installed version with `SELECT extversion FROM pg_extension WHERE extname = 'vector';`.

## When pgvector fits, and when it does not

Tradeoff, not a ranking:

- **pgvector dominates when** vectors belong with relational data: you need
  transactional consistency between an embedding and its source row, SQL
  filtering and joins, one system to back up and secure, and your corpus fits
  on a PostgreSQL instance you can size.
- **A dedicated vector database may make more sense when** the corpus is very
  large relative to what one PostgreSQL node (plus replicas or sharding) can
  hold in memory, you need specialized ANN features (specific quantization,
  very high-QPS filtered search, built-in sharding of vector indexes), or the
  vector workload would compete with your OLTP workload for the same resources.
- Measure on your own data and query mix. Retrieval quality depends first on
  your chunking and embedding model, and only then on the index.

## Where to go next

- Index mechanics in general: [03-database-design/indexes.md](../03-database-design/indexes.md)
- Reading plans: [05-performance/explain.md](../05-performance/explain.md)
- Vacuum behavior on frequently updated tables: [05-performance/vacuum.md](../05-performance/vacuum.md)
- Application role vs. migration role (who may `CREATE EXTENSION`): [06-security/least-privilege.md](../06-security/least-privilege.md)
- SQLAlchemy patterns: [08-python-fastapi/sqlalchemy.md](../08-python-fastapi/sqlalchemy.md)
- Agent memory in PostgreSQL: [11-agentic-ai/conversation-memory.md](../11-agentic-ai/conversation-memory.md)
