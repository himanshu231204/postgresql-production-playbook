# Foreign Keys

## What it is

A constraint that ties a column (or columns) in one table to a
primary/unique key in another, enforced by the database itself.

## Why it matters

A foreign key is the difference between "the application is supposed to
keep this consistent" and "the database guarantees it." Application bugs
happen; a foreign key constraint catches the ones that would otherwise
leave orphaned or inconsistent rows.

## Syntax

```sql
CREATE TABLE orders (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  customer_id BIGINT NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
  ...
);
```

## `ON DELETE`/`ON UPDATE` actions

| Action | Behavior when the referenced row is deleted/updated |
|---|---|
| `RESTRICT` | Block the delete/update if any referencing row exists (the default without `ON DELETE`/`ON UPDATE` behaves like `NO ACTION`, which is checked at the end of the statement/transaction rather than immediately — practically similar for most application purposes) |
| `NO ACTION` | Same effect as `RESTRICT` for most purposes; differs only in exactly when the check runs relative to other operations in the same statement |
| `CASCADE` | Delete/update the referencing rows too |
| `SET NULL` | Set the referencing column to `NULL` |
| `SET DEFAULT` | Set the referencing column to its default value |

## Common mistakes

- **Not indexing the foreign key column.** PostgreSQL requires an index
  on the *referenced* column (it's usually the primary key, already
  indexed) but does **not** automatically create one on the
  *referencing* column. Without it, deleting a row from the parent table
  forces a full scan of the child table to check for references, and
  joins on the FK are slower than they need to be:

  ```sql
  CREATE INDEX ON orders (customer_id);
  ```

- **`ON DELETE CASCADE` cascading further than intended.** Deleting a
  `users` row with `ON DELETE CASCADE` on every table referencing it can
  silently delete data you meant to keep (e.g. audit logs). Use
  `RESTRICT` or `SET NULL` for anything that should survive the parent's
  deletion, and reserve `CASCADE` for genuinely dependent data.
- Adding a foreign key to a large, already-populated production table
  without considering the validation cost — see "Production
  considerations."

## Production considerations

Adding a foreign key to a table with existing data requires PostgreSQL to
scan and validate every existing row, which holds a lock for the
duration. For a large table, add it in two steps to avoid a long-held
blocking lock:

```sql
-- Step 1: add the constraint without validating existing rows (fast, brief lock)
ALTER TABLE orders
  ADD CONSTRAINT orders_customer_id_fkey
  FOREIGN KEY (customer_id) REFERENCES customers(id) NOT VALID;

-- Step 2: validate separately — takes a lighter lock that doesn't block writes
ALTER TABLE orders VALIDATE CONSTRAINT orders_customer_id_fkey;
```

New rows are checked against the constraint immediately after step 1;
only the scan of *existing* rows is deferred to step 2.

## Quick revision

- Index the referencing column yourself — PostgreSQL doesn't do it
  automatically.
- Pick `ON DELETE` deliberately per relationship; don't default to
  `CASCADE` everywhere.
- Add a FK to a large table with `NOT VALID` + `VALIDATE CONSTRAINT` to
  avoid a long blocking lock.
