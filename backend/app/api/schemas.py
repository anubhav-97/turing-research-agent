"""Pydantic request/response/event models — the wire contract with the UI.

These mirror the TS types in ``frontend/src/types.ts``. Keep them in sync.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# --- Requests ---------------------------------------------------------------

class ChatRequest(BaseModel):
    thread_id: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=4000)

    @field_validator("message")
    @classmethod
    def _no_whitespace_only(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("message must not be empty or whitespace-only")
        return v


class ResumeRequest(BaseModel):
    thread_id: str = Field(min_length=1, max_length=64)
    clarification: str = Field(min_length=1, max_length=2000)

    @field_validator("clarification")
    @classmethod
    def _no_whitespace_only(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("clarification must not be empty or whitespace-only")
        return v


# --- SSE event payloads (the body of each ``data:`` line) -------------------

EventType = Literal[
    "node_start",
    "node_end",
    "interrupt",
    "final_message",
    "error",
    "ping",
]


class SSEEvent(BaseModel):
    """Envelope sent in every SSE ``data:`` line."""

    type: EventType
    node: str | None = None
    state_delta: dict[str, Any] | None = None
    question: str | None = None  # for type="interrupt"
    content: str | None = None  # for type="final_message"
    message: str | None = None  # for type="error"


# --- Thread history response ------------------------------------------------

class MessageSnapshot(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    name: str | None = None


class ThreadHistory(BaseModel):
    thread_id: str
    messages: list[MessageSnapshot]
    interrupted: bool
    pending_question: str | None = None
