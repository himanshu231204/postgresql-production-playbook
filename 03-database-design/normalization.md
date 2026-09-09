# Normalization

## What it is

Structuring tables to avoid storing the same fact in more than one
place, so an update can't create an inconsistency. Deliberate
denormalization is the opposite: accepting some duplication in exchange
for read performance or simplicity.

## Why it matters

Under-normalized data drifts inconsistent over time (an address stored
on both the `orders` and `customers` tables can disagree after an
update). Over-normalized data requires joining many tables for even
simple, frequent reads.

## The normal forms, briefly

| Form | Rule | Violation example |
|---|---|---|
| 1NF | Each column holds one atomic value, no repeating groups | A `tags` column storing `"a,b,c"` as a single string |
| 2NF | Every non-key column depends on the *whole* primary key, not part of a composite key | In a table keyed on `(order_id, product_id)`, storing `product_name` (depends only on `product_id`) |
| 3NF | No non-key column depends on another non-key column | Storing both `zip_code` and `city` when `city` is fully determined by `zip_code` |

Most application schemas aim for 3NF by default, then deliberately
denormalize specific, identified hot paths.

## Production usage: deliberate denormalization

Common, justified denormalization patterns:

- A cached/duplicated column to avoid a join on a hot read path (e.g.
  storing `customer_name` on `orders` alongside `customer_id`) — only
  worth it once you've confirmed the join is actually a bottleneck (see
  [05-performance/explain.md](../05-performance/explain.md)).
- A precomputed aggregate (e.g. `orders_count` on `customers`) updated by
  a trigger or application code, instead of `count(*)` on every read.
- JSONB columns for genuinely variable, application-defined structure
  (see below) instead of forcing a rigid relational shape onto it.

Every denormalized value needs an explicit answer to "what keeps this in
sync, and what happens if it drifts?" — a trigger, an application-level
write path, or a periodic reconciliation job. Denormalizing without that
answer just defers the inconsistency problem.

## JSONB as a controlled escape hatch

PostgreSQL's `JSONB` type is a legitimate way to store data whose shape
genuinely varies per row (arbitrary metadata, an LLM tool call's
arguments) without forcing normalization onto something that doesn't
have a stable shape:

```sql
CREATE TABLE tool_calls (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  tool_name TEXT NOT NULL,
  arguments JSONB NOT NULL,
  result JSONB
);
```

This is a tool for genuinely variable data, not a substitute for schema
design — a column with a fixed, known shape belongs in its own typed
column, not buried inside a JSONB blob, because typed columns get
constraints, indexes, and query planner statistics that JSONB fields
don't get as easily.

## Common mistakes

- Normalizing to the point that a common, hot-path query needs five or
  more joins, without ever measuring whether that's actually a problem.
- Denormalizing a value with no defined mechanism to keep it in sync —
  it silently drifts stale.
- Reaching for a JSONB column to avoid deciding on a schema, for data
  that actually does have a consistent, knowable shape.

## AI/agentic use case

Storing an LLM's tool-call arguments and results as `JSONB` (rather than
trying to normalize an arbitrary, per-tool argument shape into columns)
is the standard pattern — see
[11-agentic-ai/tool-calls.md](../11-agentic-ai/tool-calls.md). Per
[AGENTS.md](../AGENTS.md#12-agentic-ai-database-rules), validate that
JSONB content before trusting it downstream — storing it as JSONB
doesn't make it safe to use unchecked.

## Quick revision

- 3NF is a reasonable default; denormalize specific, measured hot paths
  deliberately, not by default.
- Every denormalized value needs an answer to "what keeps it in sync?"
- JSONB is for genuinely variable data, not a way to skip schema design
  for data that has a known shape.
