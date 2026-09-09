# Constraints

## What it is

Rules enforced by the database on every write: `NOT NULL`, `UNIQUE`,
`CHECK`, and (briefly covered here) `EXCLUDE`.

## Why it matters

A constraint enforced in the database catches every write path —
application bugs, a forgotten validation in a new code path, a manual
`psql` fix during an incident. Application-level-only validation catches
none of those.

## Syntax

```sql
CREATE TABLE subscriptions (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  customer_id BIGINT NOT NULL REFERENCES customers(id),
  plan TEXT NOT NULL CHECK (plan IN ('free', 'pro', 'enterprise')),
  seats INT NOT NULL CHECK (seats > 0),
  external_ref TEXT UNIQUE
);
```

## `UNIQUE` and `NULL`s

Standard SQL treats `NULL` as never equal to anything, including another
`NULL` — so a plain `UNIQUE` constraint allows multiple rows with `NULL`
in that column:

```sql
CREATE TABLE users (email TEXT UNIQUE);
-- Both of these succeed — NULL doesn't count as a duplicate by default:
INSERT INTO users (email) VALUES (NULL);
INSERT INTO users (email) VALUES (NULL);
```

PostgreSQL 15+ added `NULLS NOT DISTINCT` to change that when you want
"only one `NULL` allowed" instead:

```sql
CREATE TABLE users (email TEXT UNIQUE NULLS NOT DISTINCT);
```

## `EXCLUDE` constraints (brief)

For "no two rows may overlap" rules that `UNIQUE`/`CHECK` can't express —
classically, no two bookings for the same room can overlap in time:

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;
ALTER TABLE bookings ADD CONSTRAINT no_overlap
  EXCLUDE USING gist (room_id WITH =, during WITH &&);
```

This needs a GiST index and the `btree_gist` extension for the plain
equality part (`room_id WITH =`); full range-type/exclusion design is
outside this page's scope.

## Common mistakes

- Assuming `UNIQUE` blocks duplicate `NULL`s — it doesn't, unless you add
  `NULLS NOT DISTINCT` (PostgreSQL 15+).
- Validating a rule only in application code when it could be a `CHECK`
  constraint — the database-enforced version can't be bypassed by a
  script, a different service, or a manual fix.
- Adding a `CHECK`/`NOT NULL` constraint to a large, populated production
  table without considering the validation cost — same concern as adding
  a foreign key (see
  [foreign-keys.md](foreign-keys.md#production-considerations)); `CHECK`
  constraints support the same `NOT VALID` + `VALIDATE CONSTRAINT`
  two-step pattern.

## Quick revision

- `NOT NULL`, `UNIQUE`, `CHECK` enforce invariants at the database level
  — prefer them over application-only validation for anything that must
  always hold.
- `UNIQUE` allows multiple `NULL`s by default; use `NULLS NOT DISTINCT`
  (PostgreSQL 15+) if that's wrong for your case.
- Adding a constraint to a large existing table: use `NOT VALID` +
  `VALIDATE CONSTRAINT` to avoid a long blocking lock.
