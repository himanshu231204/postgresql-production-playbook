"""Tool registry with strict argument validation, plus a stubbed model.

LLM output is untrusted input. Every tool call is checked against a Pydantic
schema BEFORE it reaches the database. Unknown tools and unknown fields are
rejected (extra="forbid"); values are bound as query parameters, never
formatted into SQL.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class CloseTicketArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    ticket_id: int = Field(gt=0)
    resolution: str = Field(min_length=1, max_length=500)


class LookupTicketArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    ticket_id: int = Field(gt=0)


TOOL_SCHEMAS: dict[str, type[BaseModel]] = {
    "close_ticket": CloseTicketArgs,
    "lookup_ticket": LookupTicketArgs,
}


class ToolRejected(Exception):
    """Raised when model output fails validation. Nothing was written."""


def validate_tool_call(tool_name: str, raw_args: Any) -> dict[str, Any]:
    """Return validated, JSON-serializable arguments or raise ToolRejected."""
    schema = TOOL_SCHEMAS.get(tool_name)
    if schema is None:
        raise ToolRejected(f"unknown tool {tool_name!r}")
    try:
        return schema.model_validate(raw_args).model_dump()
    except ValidationError as exc:
        raise ToolRejected(f"invalid arguments for {tool_name}: {exc.error_count()} error(s)") from exc


def stub_model(ticket_id: int, *, hostile: bool = False) -> dict[str, Any]:
    """Stand-in for an LLM response. No API key, no network.

    hostile=True simulates a prompt-injected model emitting extra fields and an
    injection payload; validation must stop it.
    """
    if hostile:
        return {
            "tool": "close_ticket",
            "arguments": {
                "ticket_id": ticket_id,
                "resolution": "done'; DROP TABLE agent.support_tickets; --",
                "status": "admin",
            },
        }
    return {
        "tool": "close_ticket",
        "arguments": {"ticket_id": ticket_id, "resolution": "Password reset link sent."},
    }
