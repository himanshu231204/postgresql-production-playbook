# SELECT

## What it is

The statement that reads rows from one or more tables.

## Why it matters

It's the most-run statement against any production database, and the one
most exposed to user input — most SQL injection vulnerabilities happen in
a `SELECT`'s `WHERE` clause.

## Syntax

```sql
SELECT [DISTINCT] col1, col2, ...
FROM table
WHERE condition
ORDER BY col [ASC|DESC] [NULLS FIRST|LAST]
LIMIT n OFFSET m;
```

`SELECT DISTINCT ON (col) ...` is a PostgreSQL extension: it returns the
first row (per `ORDER BY`) for each distinct value of `col` — useful for
"latest row per group" queries without a window function.

## Example

```sql
SELECT id, email, created_at
FROM users
WHERE status = 'active'
ORDER BY created_at DESC
LIMIT 20;
```

## Production usage

For pagination past the first page, prefer **keyset pagination** over
`LIMIT`/`OFFSET`:

```sql
-- Offset pagination: PostgreSQL still scans and discards the first 10,000 rows.
SELECT id, email FROM users ORDER BY id LIMIT 20 OFFSET 10000;

-- Keyset pagination: uses an index on id directly, cost independent of page depth.
SELECT id, email FROM users WHERE id > 10000 ORDER BY id LIMIT 20;
```

`OFFSET` gets linearly slower the deeper you paginate, because the server
still has to generate and discard every skipped row. Keyset pagination
(also called cursor-based pagination) carries the last-seen key forward
instead, so cost stays flat. See
[05-performance/query-optimization.md](../05-performance/query-optimization.md).

## Common mistakes

- Writing `WHERE col = NULL` — always false, even when `col` is `NULL`.
  Use `WHERE col IS NULL`.
- `SELECT *` in application code — breaks silently when a column is added
  or reordered, and fetches data you don't need.
- Reaching for `OFFSET` pagination on a table that will grow past a few
  thousand rows.
- Assuming `ORDER BY` without a tiebreaker gives stable results — if two
  rows tie on the sort column, their relative order is not guaranteed
  unless you add a unique tiebreaker column (e.g. `ORDER BY created_at, id`).

## Security considerations

Never build a query by string-concatenating user input:

```python
# BAD — SQL injection
cursor.execute(f"SELECT * FROM users WHERE email = '{email}'")

# GOOD — parameterized query; the driver escapes the value
cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
```

This applies identically to values that came from an LLM's output — see
"AI/agentic use case" below.

## Performance considerations

- An index on the `WHERE`/`ORDER BY` columns is what makes both filtering
  and keyset pagination fast — see
  [03-database-design/indexes.md](../03-database-design/indexes.md).
- Check what PostgreSQL is actually doing with
  [05-performance/explain.md](../05-performance/explain.md) rather than
  guessing.

## AI/agentic use case

Never interpolate an LLM-produced value directly into a `SELECT` — treat
it exactly like untrusted user input: pass it as a bound parameter, and
validate/allowlist it if it's meant to select a column or table name
(which can't be parameterized the same way values can). See
[AGENTS.md](../AGENTS.md#12-agentic-ai-database-rules).

## Troubleshooting

| Symptom | Cause |
|---|---|
| `column "Foo" does not exist` | Unquoted identifiers are folded to lowercase; `Foo` needs `"Foo"` if the column was created quoted |
| A row you expect is missing from `WHERE col = NULL` results | Use `IS NULL`, not `= NULL` |
| Pagination gets slower on later pages | `OFFSET`-based pagination — switch to keyset pagination |

## Quick revision

- `IS NULL`/`IS NOT NULL`, never `= NULL`.
- `DISTINCT ON` for "one row per group" without a window function.
- Keyset pagination beats `OFFSET` for anything beyond a small table.
- Always parameterize — never string-concatenate a query.
