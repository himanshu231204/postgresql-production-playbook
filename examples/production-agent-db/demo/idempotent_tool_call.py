"""Demo 1: idempotent tool calls via UNIQUE (run_id, idempotency_key).

Two workers race to execute the SAME logical tool call. The INSERT ... ON
CONFLICT DO NOTHING guard makes exactly one of them run the side effect; the
loser waits for the winner's transaction and returns the stored result.

Limit: if the external side effect succeeds and the commit then fails, a retry
re-runs it. Pass the idempotency key to the downstream system too.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from db import connect, seed_run
from tools import ToolRejected, validate_tool_call

SIDE_EFFECT_LOG: list[str] = []  # stands in for an email / payment API


def send_reset_email(ticket_id: int) -> dict[str, Any]:
    time.sleep(0.5)  # hold the transaction open so the race is real
    SIDE_EFFECT_LOG.append(f"email for ticket {ticket_id}")
    return {"sent": True}


def execute_tool_call(
    conn: psycopg.Connection[dict[str, Any]],
    run_id: Any,
    idempotency_key: str,
    tool_name: str,
    raw_args: Any,
) -> dict[str, Any]:
    args = validate_tool_call(tool_name, raw_args)  # untrusted input: validate first
    with conn.transaction():
        claimed = conn.execute(
            """
            INSERT INTO tool_calls (run_id, idempotency_key, tool_name, arguments, status, attempts)
            VALUES (%s, %s, %s, %s, 'running', 1)
            ON CONFLICT (run_id, idempotency_key) DO NOTHING
            RETURNING id
            """,
            (run_id, idempotency_key, tool_name, Jsonb(args)),
        ).fetchone()
        if claimed is None:
            existing = conn.execute(
                "SELECT status, arguments, result FROM tool_calls "
                "WHERE run_id = %s AND idempotency_key = %s",
                (run_id, idempotency_key),
            ).fetchone()
            assert existing is not None
            if existing["arguments"] != args:
                raise ToolRejected("idempotency key reused with different arguments")
            return {"replayed": True, "status": existing["status"], "result": existing["result"]}
        result = send_reset_email(args["ticket_id"]) if tool_name == "close_ticket" else {}
        conn.execute(
            "UPDATE tool_calls SET status = 'succeeded', result = %s, completed_at = now() WHERE id = %s",
            (Jsonb(result), claimed["id"]),
        )
        return {"replayed": False, "status": "succeeded", "result": result}


def main() -> None:
    with connect() as setup_conn:
        ids = seed_run(setup_conn)
    outcomes: list[dict[str, Any]] = []

    def worker() -> None:
        with connect() as conn:
            outcomes.append(
                execute_tool_call(
                    conn,
                    ids["run_id"],
                    "step-3:close_ticket",
                    "close_ticket",
                    {"ticket_id": ids["ticket_id"], "resolution": "Reset link sent."},
                )
            )

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    with connect() as conn:
        count = conn.execute(
            "SELECT count(*) AS n FROM tool_calls WHERE run_id = %s", (ids["run_id"],)
        ).fetchone()
    print("outcomes:", sorted(o["replayed"] for o in outcomes))
    print("side effects executed:", len(SIDE_EFFECT_LOG))
    print("tool_calls rows:", count["n"] if count else None)
    assert len(SIDE_EFFECT_LOG) == 1 and count and count["n"] == 1
    print("OK: exactly-once execution")


if __name__ == "__main__":
    main()
