"""Demo 4: agent state and business data in ONE transaction.

close_ticket changes the business row (support_tickets), records the tool call
result, advances workflow_state and writes an audit row atomically. If any
step fails, everything rolls back and the retry starts clean. Also shows
validation rejecting a hostile (prompt-injected) model output before any write.
"""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from db import connect, seed_run
from tools import ToolRejected, stub_model, validate_tool_call


def close_ticket(
    conn: psycopg.Connection[dict[str, Any]],
    ids: dict[str, Any],
    key: str,
    raw_args: Any,
    *,
    fail_after_business_write: bool = False,
) -> None:
    args = validate_tool_call("close_ticket", raw_args)
    with conn.transaction():
        conn.execute("SELECT set_config('agent.actor', %s, true)", (f"run:{ids['run_id']}",))
        call = conn.execute(
            "INSERT INTO tool_calls (run_id, idempotency_key, tool_name, arguments, status, attempts) "
            "VALUES (%s, %s, 'close_ticket', %s, 'running', 1) "
            "ON CONFLICT (run_id, idempotency_key) DO NOTHING RETURNING id",
            (ids["run_id"], key, Jsonb(args)),
        ).fetchone()
        if call is None:
            return  # already executed by an earlier attempt
        # Ownership check in SQL: only this user's open ticket may be closed.
        updated = conn.execute(
            "UPDATE support_tickets SET status = 'closed', resolution = %s, closed_by_tool_call = %s "
            "WHERE id = %s AND user_id = %s AND status = 'open'",
            (args["resolution"], call["id"], args["ticket_id"], ids["user_id"]),
        )
        if updated.rowcount != 1:
            raise ToolRejected("ticket not found, not owned by this user, or already closed")
        if fail_after_business_write:
            raise RuntimeError("simulated crash before commit")
        conn.execute(
            "UPDATE tool_calls SET status = 'succeeded', result = %s, completed_at = now() WHERE id = %s",
            (Jsonb({"closed": args["ticket_id"]}), call["id"]),
        )
        conn.execute(
            "UPDATE workflow_state SET step = 'ticket_closed', version = version + 1, updated_at = now() "
            "WHERE run_id = %s",
            (ids["run_id"],),
        )
        conn.execute(
            "INSERT INTO audit_logs (actor_type, actor_id, action, entity_type, entity_id, details) "
            "VALUES ('agent', %s, 'ticket.closed', 'support_tickets', %s, %s)",
            (f"run:{ids['run_id']}", str(args["ticket_id"]), Jsonb({"tool_call_id": str(call["id"])})),
        )


def snapshot(conn: psycopg.Connection[dict[str, Any]], ids: dict[str, Any]) -> tuple[str, int]:
    t = conn.execute("SELECT status FROM support_tickets WHERE id = %s", (ids["ticket_id"],)).fetchone()
    c = conn.execute("SELECT count(*) AS n FROM tool_calls WHERE run_id = %s", (ids["run_id"],)).fetchone()
    conn.commit()
    assert t is not None and c is not None
    return t["status"], c["n"]


def main() -> None:
    with connect() as conn:
        ids = seed_run(conn)
        call = stub_model(ids["ticket_id"], hostile=True)
        try:
            close_ticket(conn, ids, "step-1", call["arguments"])
        except ToolRejected as exc:
            print("hostile output rejected:", exc)
        print("after rejection:", snapshot(conn, ids))

        call = stub_model(ids["ticket_id"])
        try:
            close_ticket(conn, ids, "step-1", call["arguments"], fail_after_business_write=True)
        except RuntimeError as exc:
            print("attempt 1 failed:", exc)
        status, n = snapshot(conn, ids)
        print("after rollback:", (status, n))
        assert (status, n) == ("open", 0)

        close_ticket(conn, ids, "step-1", call["arguments"])
        close_ticket(conn, ids, "step-1", call["arguments"])  # replay is a no-op
        status, n = snapshot(conn, ids)
        print("after retry + replay:", (status, n))
        assert (status, n) == ("closed", 1)
        audit = conn.execute(
            "SELECT action FROM audit_logs WHERE entity_id IN (%s, %s) ORDER BY id",
            (str(ids["ticket_id"]), str(ids["run_id"])),
        ).fetchall()
        print("audit actions:", [r["action"] for r in audit])
    print("OK: state and business data committed atomically")


if __name__ == "__main__":
    main()
