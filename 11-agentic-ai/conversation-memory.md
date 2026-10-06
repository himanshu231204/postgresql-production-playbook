# Conversation Memory

## What it is

Persisting what an agent has said and heard (`conversations`, `messages`),
selecting what goes back into the prompt, and optionally adding semantic
long-term memory with pgvector.

## Why it matters

LLM calls are stateless: every request must carry the relevant history.
The database defines the ordering guarantees, what can be reconstructed
after a crash, how much you retain (cost and PII), and who can see whose
memory.

## Messages

Table (from `010_schema.sql`): `messages(id, conversation_id, run_id, seq,
role, content, token_count, created_at)` with `UNIQUE (conversation_id, seq)`
and `role IN ('system','user','assistant','tool')`.

Order by `seq`, not `created_at`: timestamps tie or skew across workers.
The unique constraint is the safety net; allocating `seq` correctly
requires serialising writers per conversation.

### Appending with the next `seq`

**PostgreSQL SQL**, PostgreSQL 16, read committed (the default):

```sql
BEGIN;
SELECT id FROM conversations WHERE id = $1 FOR UPDATE;   -- statement 1: take the row lock
INSERT INTO messages (conversation_id, seq, role, content, token_count)
SELECT $1, coalesce(max(seq), 0) + 1, $2, $3, $4          -- statement 2: sees committed rows
FROM messages WHERE conversation_id = $1
RETURNING seq;
COMMIT;
```

The lock and the `max(seq)` read must be separate statements. Tested with
two sessions: when both were combined into one statement (lock in a CTE),
the waiting writer used a snapshot taken before the wait, computed the
same `seq`, and failed with `duplicate key value violates unique
constraint "messages_conversation_id_seq_key"` (the constraint did its
job). With the two-statement form the writers got `seq` 3 and 4.

Alternatives and tradeoffs:

| Approach | Pro | Con |
|---|---|---|
| Lock conversation row, `max(seq) + 1` (above) | No schema change; strict gapless order | Serialises writers per conversation; row lock held until commit |
| `last_seq` counter on `conversations` (`UPDATE ... SET last_seq = last_seq + 1 RETURNING last_seq`) | One statement; lock is implicit | Extra column; update on a hot row creates dead tuples |
| Retry on unique violation | No explicit lock | Application retry logic; wasted work under contention |
| Identity/sequence per message, order by `id` | Simplest, no contention | Not per-conversation; gaps; order is commit-unrelated across concurrent writers |

Messages for one conversation are written by one run at a time in most
agent designs; contention is then rare and any option works.

### Loading context

```sql
-- Last 20 messages, returned in chronological order. Uses the UNIQUE (conversation_id, seq) index.
SELECT seq, role, content
FROM (SELECT seq, role, content FROM messages
      WHERE conversation_id = $1 ORDER BY seq DESC LIMIT 20) recent
ORDER BY seq;
```

Selecting by message count is crude: select by `token_count` budget
(running sum) when context size matters. `token_count` is whatever your
tokenizer reports; it must match the target model's tokenizer to be
reliable.

### Strategies for long conversations

| Strategy | How | Tradeoff |
|---|---|---|
| Sliding window | Last N messages / token budget | Cheap; forgets early facts |
| Rolling summary | Store a summary row (`role = 'system'`, or a separate `conversation_summaries` table you add) and keep recent messages verbatim | Fewer tokens; summaries lose detail and can be wrong; they are model output, so treat as untrusted data |
| Semantic retrieval | Embed messages/facts, fetch top-k similar | Recall depends on chunking and embedding quality; needs pgvector |
| Hybrid | Window + summary + retrieval | Most complex to debug |

## Retention and partitioning

`messages` and `tool_calls.result` are the largest tables in an agent
system and contain user text (PII, possibly secrets pasted by users).
Decide retention per table before launch.

Options:

| Option | Mechanism | Pro | Con |
|---|---|---|---|
| Keep forever | Nothing | Full audit and eval history | Unbounded growth; privacy exposure; slower vacuum and backups |
| Batched `DELETE` by age | Scheduled job | Simple | Bloat and WAL; needs autovacuum tuning ([05-performance/vacuum.md](../05-performance/vacuum.md)); slow at scale |
| Time partitioning + `DROP`/detach | `PARTITION BY RANGE (created_at)` | Dropping an old partition is fast and avoids bloat | Primary key and unique constraints must include the partition key; foreign keys *to* the partitioned table are constrained; partition creation must be automated |
| Archive then delete | Copy to cold storage, then drop | Keeps history cheaply | Pipeline to maintain; restore path to design |

Batched delete (**destructive**, rows are permanently removed; confirm
retention policy and run a `SELECT count(*)` with the same predicate first;
run off-peak; take a backup per [07-backups-recovery/](../07-backups-recovery/README.md)):

```sql
WITH old AS (
    SELECT id FROM messages
    WHERE created_at < now() - interval '365 days'     -- illustrative retention
    LIMIT 1000
    FOR UPDATE SKIP LOCKED
)
DELETE FROM messages m USING old WHERE m.id = old.id;
```

Tested (zero rows matched on the empty example data; syntax and plan valid).

### Partitioned messages

Version: PostgreSQL 16 (`DETACH PARTITION ... CONCURRENTLY` requires 14+).
Tested as a standalone table:

```sql
CREATE TABLE messages_p (
    id              bigint GENERATED ALWAYS AS IDENTITY,
    conversation_id uuid        NOT NULL,
    seq             integer     NOT NULL CHECK (seq > 0),
    role            text        NOT NULL CHECK (role IN ('system','user','assistant','tool')),
    content         text        NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (id, created_at),                       -- must include the partition key
    UNIQUE (conversation_id, seq, created_at)           -- uniqueness is per partition key range only
) PARTITION BY RANGE (created_at);

CREATE TABLE messages_p_2026_10 PARTITION OF messages_p
    FOR VALUES FROM ('2026-10-01') TO ('2026-11-01');
CREATE TABLE messages_p_2026_11 PARTITION OF messages_p
    FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');
```

Expected: a query with a `created_at` range scans only matching
partitions (verified with `EXPLAIN`: only `messages_p_2026_11`).

```sql
-- Retire a month. DESTRUCTIVE (DROP TABLE): the data is gone unless archived or backed up.
ALTER TABLE messages_p DETACH PARTITION messages_p_2026_10 CONCURRENTLY;
-- archive it (pg_dump / COPY), verify, then:
DROP TABLE messages_p_2026_10;
```

Caveats (verified or documented behavior):

- `DETACH ... CONCURRENTLY` failed with `cannot detach partitions concurrently when a default partition exists` in testing; either skip the `DEFAULT` partition (inserts outside any range then fail, so automate partition creation ahead of time) or use plain `DETACH PARTITION` (takes a stronger lock).
- The unique key becomes `(conversation_id, seq, created_at)`: it no longer guarantees `(conversation_id, seq)` uniqueness across partitions. Messages of one conversation spanning a boundary can collide. Enforce ordering in the writer (lock + `max(seq)`) and/or keep a counter on `conversations`.
- Do not pair this with foreign keys from other tables to `messages_p`; reference `conversation_id` only.
- Partitioning pays off when you actually drop or archive by time at large scale. For modest volumes a plain table with batched deletes is simpler. Cost model: more objects, planner overhead per partition, migration effort to convert an existing table.

Converting the example `messages` table is a migration with locking and
backfill implications: see [09-alembic/production-migrations.md](../09-alembic/production-migrations.md).

## Vector memory with pgvector

Semantic memory = store embeddings of messages or extracted facts, retrieve
the nearest ones per turn. Full coverage lives in
[10-pgvector/README.md](../10-pgvector/README.md),
[embeddings.md](../10-pgvector/embeddings.md),
[similarity-search.md](../10-pgvector/similarity-search.md), and the worked
[rag-example.md](../10-pgvector/rag-example.md). Sketch only; **not
executed in this repo's validation run** (the pgvector extension was not
installed in the test environment, so verify with the pgvector pages'
tested patterns before use). PostgreSQL 16 with pgvector installed:

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE memory_items (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id         uuid        NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    conversation_id uuid        REFERENCES conversations (id) ON DELETE SET NULL,
    source_message_id bigint    REFERENCES messages (id) ON DELETE SET NULL,
    content         text        NOT NULL,
    embedding       vector(1536) NOT NULL,   -- dimension MUST equal the embedding model's output
    embedding_model text        NOT NULL,   -- vectors from different models are not comparable
    created_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX memory_items_embedding_hnsw
    ON memory_items USING hnsw (embedding vector_cosine_ops);   -- cosine: common for text embeddings

-- Retrieval, always scoped to the caller:
SELECT content, embedding <=> $1 AS cosine_distance
FROM memory_items
WHERE user_id = $2
ORDER BY embedding <=> $1
LIMIT 5;
```

Points specific to agents:

- Scope every retrieval by `user_id` (and tenant). Cross-user leakage through shared memory is the main security risk. With an approximate index and a selective filter, the index may return fewer rows than `LIMIT`; see the filtering section in [similarity-search.md](../10-pgvector/similarity-search.md).
- Index choice (HNSW vs IVFFlat) is a tradeoff of build time and memory against recall and speed: see [10-pgvector/indexing.md](../10-pgvector/indexing.md).
- Store `embedding_model` and re-embed on model change; mixed models in one column give meaningless distances.
- Retrieved text is untrusted: it re-enters the prompt, so a poisoned memory is an injection vector ([tool-calls.md](tool-calls.md#prompt-injection-implications-for-the-db-layer)).
- Retrieval quality depends on what you embed (chunking, extracting facts versus raw turns) and on the embedding model, not just the index.
- A dedicated vector database may fit better at very large scale or with specialised ANN needs; pgvector's advantage is one system and transactional consistency with `messages` and `users` (delete a user's data once, in one transaction).

## Security considerations

- Messages hold PII. Apply retention, restrict `SELECT`, and provide an erasure procedure (the example uses `ON DELETE RESTRICT` on `users`, so erasure is an explicit admin-run script that deletes dependent rows, then the user).
- Do not store secrets in message content; redact before insert if users may paste credentials.
- `role = 'tool'` rows contain third-party data; mark provenance and treat as untrusted when re-prompting.

## Performance considerations

- The `(conversation_id, seq)` unique index serves both the order and "last N" lookups; verify with `EXPLAIN`.
- Wide `content` values are TOASTed; avoid `SELECT *` on lists.
- Appends only touch the tail of the index per conversation; an index on `created_at` alone is not in the example because no query needs it.

## Common mistakes

- Ordering by `created_at`.
- Combining the lock and the `max(seq)` read in one statement.
- Whole transcript in one JSONB column (every append rewrites it; no per-message constraints).
- Retrieval without a user/tenant filter.
- Re-using vectors after switching embedding models.

## Quick revision

- Order by `seq`; lock the conversation row in a separate statement before reading `max(seq)`.
- Window, summary, retrieval are tradeoffs, not a hierarchy.
- Retention is a design decision: batched delete is simple, partitioning is fast but constrains keys.
- Vector memory: scope by user, record the model, link to [10-pgvector](../10-pgvector/README.md).
