"""Connection and seed helpers shared by the demos (psycopg 3, PostgreSQL 16)."""

from __future__ import annotations

import os
import uuid
from typing import Any

import psycopg
from psycopg.rows import dict_row


def connect() -> psycopg.Connection[dict[str, Any]]:
    """Open a transactional connection using DATABASE_URL (never hardcoded)."""
    try:
        url = os.environ["DATABASE_URL"]
    except KeyError as exc:
        raise SystemExit("DATABASE_URL is not set; see .env.example") from exc
    return psycopg.connect(url, row_factory=dict_row)


def seed_run(conn: psycopg.Connection[dict[str, Any]]) -> dict[str, Any]:
    """Create a user, conversation, run and open ticket. Returns their ids."""
    with conn.transaction():
        user = conn.execute(
            "INSERT INTO users (external_ref, display_name) VALUES (%s, %s) RETURNING id",
            (f"demo-{uuid.uuid4()}", "Demo User"),
        ).fetchone()
        assert user is not None
        conv = conn.execute(
            "INSERT INTO conversations (user_id, title) VALUES (%s, %s) RETURNING id",
            (user["id"], "demo"),
        ).fetchone()
        assert conv is not None
        run = conn.execute(
            "INSERT INTO agent_runs (conversation_id, agent_version, status, started_at) "
            "VALUES (%s, %s, 'running', now()) RETURNING id",
            (conv["id"], "demo-0.1"),
        ).fetchone()
        assert run is not None
        ticket = conn.execute(
            "INSERT INTO support_tickets (user_id, subject) VALUES (%s, %s) RETURNING id",
            (user["id"], "Cannot log in"),
        ).fetchone()
        assert ticket is not None
        conn.execute(
            "INSERT INTO workflow_state (run_id, workflow, step, state) VALUES (%s, %s, %s, %s)",
            (run["id"], "triage", "start", psycopg.types.json.Jsonb({})),
        )
    return {
        "user_id": user["id"],
        "conversation_id": conv["id"],
        "run_id": run["id"],
        "ticket_id": ticket["id"],
    }
