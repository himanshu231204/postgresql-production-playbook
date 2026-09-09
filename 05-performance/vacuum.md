# VACUUM and Autovacuum

## What it is

The process that reclaims space from rows that `UPDATE`/`DELETE` left
behind, and prevents transaction ID exhaustion.

## Why it matters

PostgreSQL's MVCC model means `UPDATE`/`DELETE` never immediately erase
a row — they mark the old version as dead and leave it in place so
concurrent transactions that started before the change can still see
their own consistent snapshot. Something has to come back and reclaim
that space, or a busy table just keeps growing.

## Why dead rows exist at all

```sql
UPDATE accounts SET balance = balance - 100 WHERE id = 1;
```

This doesn't overwrite the row — it inserts a new row version and marks
the old one dead once no transaction can still need it (per
[04-transactions/isolation-levels.md](../04-transactions/isolation-levels.md)'s
MVCC snapshots). A table with heavy `UPDATE`/`DELETE` traffic
accumulates dead row versions between vacuum runs.

## `VACUUM` vs. `VACUUM FULL`

| | `VACUUM` | `VACUUM FULL` |
|---|---|---|
| What it does | Marks dead tuples' space reusable by future inserts, in place | Rewrites the entire table into a new, compact file |
| Lock taken | None that blocks concurrent reads/writes | `ACCESS EXCLUSIVE` — blocks all reads and writes for the duration |
| Reclaims space back to the OS | No — space stays allocated to the table for reuse | Yes |
| Production use | Routine, safe to run anytime (and what autovacuum does automatically) | **Destructive to availability** — see [AGENTS.md](../AGENTS.md#18-production-safety-in-content); only for a table that's severely bloated and where downtime is acceptable, or via `pg_repack`/similar for an online alternative |

Plain `VACUUM` is normal, routine maintenance. `VACUUM FULL` is a
different, much more disruptive operation that happens to share a name.

## Autovacuum

Autovacuum runs `VACUUM` (and `ANALYZE` — see [analyze.md](analyze.md))
automatically per table, based on how many rows have changed:

```
dead tuples > autovacuum_vacuum_threshold + autovacuum_vacuum_scale_factor × reltuples
```

With the defaults — `autovacuum_vacuum_threshold = 50`,
`autovacuum_vacuum_scale_factor = 0.2` — a table is vacuumed once its
dead tuples exceed roughly 20% of its row count plus 50. These defaults
work reasonably for small-to-medium tables; a very large, high-churn
table often benefits from a lower per-table `autovacuum_vacuum_scale_factor`
(set via `ALTER TABLE ... SET (autovacuum_vacuum_scale_factor = ...)`)
so it gets vacuumed more often in absolute terms rather than waiting for
20% of a huge row count to accumulate as dead tuples.

## The visibility map and index-only scans

Vacuum also maintains the visibility map, which tracks which table pages
contain only rows visible to every current transaction. An up-to-date
visibility map is what lets an index-only scan (see
[03-database-design/indexes.md](../03-database-design/indexes.md#covering-indexes-include))
skip visiting the table at all — a table that's rarely vacuumed loses
this benefit even with a covering index in place.

## Transaction ID wraparound (summary)

PostgreSQL's transaction IDs are finite and wrap around; vacuum is also
what "freezes" old row versions so their original transaction ID no
longer matters for visibility checks. An extremely long-running or
abandoned transaction doesn't just hold locks (see
[04-transactions/locking.md](../04-transactions/locking.md)) — it also
prevents vacuum from freezing/cleaning up rows newer than its snapshot,
which is one reason a stuck "idle in transaction" connection is treated
as a real production concern rather than a curiosity, not just a lock
contention issue.

## Common mistakes

- Running `VACUUM FULL` on a production table as a routine maintenance
  task — it's a heavy, blocking operation, not the normal path.
- Leaving a transaction "idle in transaction" for a long time, not
  realizing it blocks vacuum cleanup on top of holding locks.
- Assuming autovacuum's default thresholds are automatically right for
  a very large, high-churn table without checking whether it's keeping
  up.

## Troubleshooting

| Symptom | Check |
|---|---|
| A table is much larger on disk than its row count would suggest | Bloat — check `pg_stat_user_tables` for dead tuple counts and confirm autovacuum is actually running on it |
| Query plans stopped using index-only scans on a table that used to get them | Visibility map may be stale — check when the table was last vacuumed |

## Quick revision

- `VACUUM` (including autovacuum) is routine and non-blocking; `VACUUM
  FULL` is a rare, blocking, destructive-to-availability operation.
- Autovacuum triggers per table once dead tuples exceed roughly 20% of
  its rows + 50 (the defaults) — tune per-table for large, high-churn
  tables.
- A long-idle transaction blocks vacuum cleanup, not just locks.
