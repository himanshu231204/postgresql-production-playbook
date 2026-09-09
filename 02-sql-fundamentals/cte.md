# Common Table Expressions (CTEs)

## What it is

A `WITH` clause that names a subquery so it can be referenced (once, or
multiple times) later in the same statement, including recursively.

## Why it matters

CTEs make complex queries readable. But their performance behavior
changed materially in PostgreSQL 12 — a query that was fast (or slow) for
version-specific reasons can behave differently after an upgrade if you
don't know about this.

## Syntax

```sql
WITH recent_orders AS (
  SELECT * FROM orders WHERE created_at > now() - interval '7 days'
)
SELECT customer_id, count(*) FROM recent_orders GROUP BY customer_id;
```

### Recursive CTEs

```sql
WITH RECURSIVE org_chart AS (
  SELECT id, manager_id, name, 1 AS depth
  FROM employees WHERE manager_id IS NULL       -- base case: the root(s)

  UNION ALL

  SELECT e.id, e.manager_id, e.name, oc.depth + 1
  FROM employees e
  JOIN org_chart oc ON e.manager_id = oc.id      -- recursive step
)
SELECT * FROM org_chart ORDER BY depth;
```

Used for hierarchical/graph data: org charts, category trees, or (in an
agentic system) walking a `workflow_state`/task dependency graph.

## `MATERIALIZED` / `NOT MATERIALIZED` (PostgreSQL 12+)

**Before PostgreSQL 12:** every non-recursive CTE was an "optimization
fence" — PostgreSQL always computed it in full, in isolation, before the
outer query ran. This was predictable but sometimes forced a worse plan
than letting the optimizer see through it.

**From PostgreSQL 12 onward:** the planner can inline a non-recursive CTE
into the outer query (as if it were a subquery) when it's referenced only
once and has no side-effecting clauses — unless you force the old
behavior explicitly:

```sql
WITH cte AS MATERIALIZED (...)      -- force the old fencing behavior
WITH cte AS NOT MATERIALIZED (...)  -- force inlining even if referenced multiple times
```

**Why this matters in production:** a query that relied on a CTE being
computed once and reused (e.g. because it's expensive and referenced
multiple times, or because you wanted to fence off a bad sub-plan) can get
a different, sometimes worse, plan after upgrading to PostgreSQL 12+ if it
now gets inlined. If you need the old guarantee, mark the CTE
`MATERIALIZED` explicitly rather than relying on version-dependent default
behavior.

## Common mistakes

- Assuming a CTE is always computed once and reused, on PostgreSQL 12+,
  without checking — the planner may inline and re-evaluate it per
  reference instead.
- Writing a recursive CTE without a way to terminate (e.g. traversing a
  graph with a cycle) — this can loop indefinitely; consider a
  `depth`/visited-set column and a `WHERE depth < N` guard for
  production use.
- Using a CTE purely for readability and being surprised when its plan
  changes after a major-version upgrade — check
  [05-performance/explain.md](../05-performance/explain.md) before and
  after, don't assume.

## Performance considerations

If a CTE is expensive and referenced more than once in the same query,
mark it `MATERIALIZED` deliberately rather than relying on the planner's
default choice — that default can change between versions. If a CTE is
purely for naming/readability and referenced once, `NOT MATERIALIZED` (or
just PostgreSQL 12+'s default) usually gives the planner more freedom to
produce a good plan.

## AI/agentic use case

A recursive CTE is the natural way to walk a `tasks`/`workflow_state`
dependency graph to find everything blocked on a given step, or to
reconstruct an agent's full call chain from `tool_calls`. See
[11-agentic-ai/workflow-state.md](../11-agentic-ai/workflow-state.md).

## Quick revision

- `WITH name AS (...) SELECT ... FROM name;` — name a subquery for reuse.
- `WITH RECURSIVE` for hierarchical/graph traversal; always bound the
  recursion.
- PostgreSQL 12+ can inline non-recursive CTEs — use `MATERIALIZED` when
  you need the pre-12 fencing behavior back.
