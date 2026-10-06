"""Demo 3: optimistic concurrency on workflow_state with a version column.

Both workers read version N. The first UPDATE ... WHERE version = N wins and
bumps the version; the second matches zero rows, detects the conflict,
reloads, re-applies its change to the fresh state and retries.
"""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from db import connect, seed_run


class StaleStateError(Exception):
    pass


def load(conn: psycopg.Connection[dict[str, Any]], run_id: Any) -> dict[str, Any]:
    row = conn.execute(
        "SELECT step, state, version FROM workflow_state WHERE run_id = %s", (run_id,)
    ).fetchone()
    assert row is not None
    return row


def save(
    conn: psycopg.Connection[dict[str, Any]],
    run_id: Any,
    expected_version: int,
    step: str,
    state: dict[str, Any],
) -> int:
    row = conn.execute(
        """
        UPDATE workflow_state
           SET step = %s, state = %s, version = version + 1, updated_at = now()
         WHERE run_id = %s AND version = %s
        RETURNING version
        """,
        (step, Jsonb(state), run_id, expected_version),
    ).fetchone()
    conn.commit()
    if row is None:
        raise StaleStateError(f"version {expected_version} is stale")
    return int(row["version"])


def main() -> None:
    with connect() as setup:
        run_id = seed_run(setup)["run_id"]

    with connect() as a, connect() as b:
        snap_a, snap_b = load(a, run_id), load(b, run_id)
        a.commit()
        b.commit()  # end read transactions
        print("both read version", snap_a["version"], snap_b["version"])

        v = save(a, run_id, snap_a["version"], "fetched", {**snap_a["state"], "fetched": True})
        print("worker A saved, version ->", v)

        try:
            save(b, run_id, snap_b["version"], "scored", {**snap_b["state"], "score": 0.9})
        except StaleStateError as exc:
            print("worker B rejected:", exc)
            fresh = load(b, run_id)
            b.commit()
            v = save(b, run_id, fresh["version"], "scored", {**fresh["state"], "score": 0.9})
            print("worker B retried on fresh state, version ->", v)

        final = load(b, run_id)
        b.commit()
    print("final state:", final["state"], "version", final["version"])
    assert final["state"] == {"fetched": True, "score": 0.9} and final["version"] == 2
    print("OK: no lost update")


if __name__ == "__main__":
    main()
