# ACID

## What it is

The four properties a transactional database guarantees for every
transaction: **A**tomicity, **C**onsistency, **I**solation, **D**urability.

## Why it matters

These aren't abstract theory — each one maps to a specific PostgreSQL
mechanism, and each one prevents a specific, concrete failure mode you'd
otherwise have to handle yourself in application code.

## The four properties, concretely

| Property | Guarantee | PostgreSQL mechanism | What it prevents |
|---|---|---|---|
| **Atomicity** | A transaction's statements all take effect, or none do | Transaction boundaries (`BEGIN`/`COMMIT`/`ROLLBACK`) | A crash or error mid-transaction leaving a half-applied change |
| **Consistency** | A transaction can't leave the database violating its declared rules | Constraints (`CHECK`, `UNIQUE`, `NOT NULL`, foreign keys — see [03-database-design/](../03-database-design/)) | Data that violates its own schema's invariants ever being committed |
| **Isolation** | Concurrent transactions don't see each other's uncommitted changes (to a degree set by the isolation level) | MVCC (multiversion concurrency control) — see [isolation-levels.md](isolation-levels.md) | One transaction reading another's not-yet-committed (and possibly about-to-be-rolled-back) changes |
| **Durability** | Once `COMMIT` returns successfully, the change survives a crash or power loss | WAL (write-ahead log) — every change is fsynced to the log before `COMMIT` returns | A committed change silently disappearing after a crash |

## Production usage

Durability is why fsync-related settings (`fsync`, `synchronous_commit`)
matter and shouldn't be disabled casually on a production instance —
`synchronous_commit = off` trades a small amount of durability (a very
recent commit could be lost on a crash, though the database itself stays
consistent) for lower commit latency; `fsync = off` risks actual data
corruption on an unclean shutdown and is not a tradeoff worth making in
production.

## Common mistakes

- Assuming "the transaction committed" and "the data survives a crash"
  are the same guarantee if `synchronous_commit` has been turned off —
  they're not, by design, in exchange for latency.
- Relying on application-level validation alone for consistency instead
  of database constraints — see
  [AGENTS.md](../AGENTS.md#8-database-design-rules).
- Treating isolation as "transactions never see anything strange" without
  knowing which anomalies your chosen isolation level actually rules
  out — see [isolation-levels.md](isolation-levels.md).

## AI/agentic use case

Atomicity is what makes an agent's write (e.g. inserting a `tool_call`
row and updating `workflow_state`) safe to treat as a single unit — see
[transactions.md](transactions.md#aiagentic-use-case).

## Quick revision

- Atomicity → transaction boundaries. Consistency → constraints.
  Isolation → MVCC. Durability → WAL.
- `synchronous_commit = off` trades durability of the most recent commits
  for latency — know that before turning it off in production.
