-- PostgreSQL 16, pgvector extension >= 0.5 (HNSW). Embedding dimension: 384.
-- The dimension MUST match the embedding model (stub and real) and EMBEDDING_DIM.
-- Run as a role allowed to CREATE EXTENSION (see README); the app role needs only DML.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source      TEXT        NOT NULL UNIQUE,          -- e.g. file name; idempotent re-ingest key
    title       TEXT        NOT NULL,
    category    TEXT        NOT NULL,                 -- metadata filter example
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id  BIGINT      NOT NULL REFERENCES documents (id) ON DELETE CASCADE ON UPDATE CASCADE,
    chunk_index  INTEGER     NOT NULL CHECK (chunk_index >= 0),
    content      TEXT        NOT NULL,
    category     TEXT        NOT NULL,                -- denormalized from documents for filtered search
    embedding    vector(384) NOT NULL,                -- 384 dims: must match the embedding model
    embedder     TEXT        NOT NULL,                -- which model/stub produced the vector
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_id, chunk_index)
);

-- Cosine distance (<=>), matching the operator used in app/retrieval.py.
-- Serves: ORDER BY embedding <=> $1 LIMIT k (approximate, HNSW).
-- Tradeoff: slower build and more memory than IVFFlat; every INSERT also
-- updates the graph. Defaults m=16, ef_construction=64 shown explicitly.
CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw
    ON chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Serves WHERE category = ... when the planner chooses to filter first (selective
-- categories) and sort exactly. Costs extra write work; drop it if EXPLAIN shows it unused.
CREATE INDEX IF NOT EXISTS chunks_category_idx ON chunks (category);
