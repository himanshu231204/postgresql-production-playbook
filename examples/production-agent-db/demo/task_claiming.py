"""Demo 2: claim tasks with FOR UPDATE SKIP LOCKED (lease-based).

Four workers drain a queue concurrently. SKIP LOCKED lets each worker take a
different row instead of waiting on a row another worker holds. The claim is
a short transaction; the lease (lease_expires_at) covers the processing time,
and a reaper requeues expired leases from crashed workers.
"""

from __future__ import annotations

import threading
from collections import Counter
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from db import connect

QUEUE = "demo-claiming"
CLAIM_SQL = """
UPDATE tasks
   SET status = 'claimed', claimed_by = %(worker)s, claimed_at = now(),
       lease_expires_at = now() + make_interval(secs => %(lease)s),
       attempts = attempts + 1, updated_at = now()
 WHERE id = (SELECT id FROM tasks
              WHERE queue = %(queue)s AND status = 'pending' AND available_at <= now()
              ORDER BY priority DESC, available_at
              LIMIT 1
              FOR UPDATE SKIP LOCKED)
RETURNING id, payload, attempts, max_attempts
"""
REAP_SQL = """
UPDATE tasks
   SET status = CASE WHEN attempts >= max_attempts THEN 'dead' ELSE 'pending' END,
       claimed_by = NULL, claimed_at = NULL, lease_expires_at = NULL,
       last_error = 'lease expired', updated_at = now()
 WHERE queue = %(queue)s AND status = 'claimed' AND lease_expires_at < now()
RETURNING id, status
"""


def claim(conn: psycopg.Connection[dict[str, Any]], worker: str) -> dict[str, Any] | None:
    with conn.transaction():
        return conn.execute(CLAIM_SQL, {"worker": worker, "lease": 60, "queue": QUEUE}).fetchone()


def finish(conn: psycopg.Connection[dict[str, Any]], task_id: Any, worker: str) -> None:
    with conn.transaction():
        conn.execute(
            "UPDATE tasks SET status = 'succeeded', claimed_by = NULL, lease_expires_at = NULL, "
            "updated_at = now() WHERE id = %s AND claimed_by = %s",  # fenced: only the lease holder
            (task_id, worker),
        )


def main() -> None:
    with connect() as conn, conn.transaction():
        conn.execute("DELETE FROM tasks WHERE queue = %s", (QUEUE,))
        for i in range(40):
            conn.execute(
                "INSERT INTO tasks (queue, payload) VALUES (%s, %s)", (QUEUE, Jsonb({"n": i}))
            )

    processed: list[tuple[str, int]] = []
    lock = threading.Lock()

    def run_worker(name: str) -> None:
        with connect() as conn:
            while (task := claim(conn, name)) is not None:
                with lock:
                    processed.append((name, task["payload"]["n"]))
                finish(conn, task["id"], name)

    threads = [threading.Thread(target=run_worker, args=(f"worker-{i}",)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    per_task = Counter(n for _, n in processed)
    print("tasks processed:", len(processed), "| distinct:", len(per_task))
    print("per worker:", dict(Counter(w for w, _ in processed)))
    assert len(processed) == 40 and all(c == 1 for c in per_task.values())
    print("OK: every task processed exactly once, no worker blocked another")

    # Reaper: simulate a worker that crashed after claiming.
    with connect() as conn:
        with conn.transaction():
            conn.execute("INSERT INTO tasks (queue, payload) VALUES (%s, %s)", (QUEUE, Jsonb({"n": 99})))
        crashed = claim(conn, "worker-crashed")
        assert crashed is not None
        with conn.transaction():
            conn.execute("UPDATE tasks SET lease_expires_at = now() - interval '1 second' WHERE id = %s", (crashed["id"],))
            reaped = conn.execute(REAP_SQL, {"queue": QUEUE}).fetchall()
        print("reaped:", [(str(r["id"])[:8], r["status"]) for r in reaped])
        assert len(reaped) == 1 and reaped[0]["status"] == "pending"
        with conn.transaction():
            conn.execute("DELETE FROM tasks WHERE queue = %s", (QUEUE,))
    print("OK: expired lease requeued")


if __name__ == "__main__":
    main()
