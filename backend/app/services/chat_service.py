"""Streams graph execution as SSE events.

The frontend gets a live view of every node transition: ``node_start`` ->
optional ``node_end`` with the state delta -> finally either an
``interrupt`` (waiting for human input) or a ``final_message`` event.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import HTTPException
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command

from app.api.schemas import MessageSnapshot, SSEEvent, ThreadHistory
from app.graph.builder import get_graph

logger = logging.getLogger(__name__)


# Only emit state-delta fields the UI actually consumes — keeps SSE small.
_UI_DELTA_KEYS = {
    "clarity_status",
    "company_name",
    "clarification_question",
    "confidence_score",
    "attempts",
    "validation_result",
    "validation_feedback",
}


def _filter_delta(delta: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in delta.items() if k in _UI_DELTA_KEYS}


def _format_event(event: SSEEvent) -> str:
    """Return just the JSON payload — ``sse-starlette`` adds the ``data: `` prefix."""
    return event.model_dump_json(exclude_none=True)


async def stream_graph(
    thread_id: str,
    user_message: str | None,
    *,
    resume_value: str | None = None,
) -> AsyncIterator[str]:
    """Run (or resume) the graph for a thread; yield SSE frames.

    Exactly one of ``user_message`` or ``resume_value`` must be set.
    """
    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id}}

    if resume_value is not None:
        payload: Any = Command(resume=resume_value)
    elif user_message is not None:
        payload = {
            "user_query": user_message,
            "messages": [HumanMessage(content=user_message)],
        }
    else:  # pragma: no cover - guarded by API layer
        raise ValueError("stream_graph requires user_message or resume_value")

    try:
        async for update in graph.astream(payload, config=config, stream_mode="updates"):
            for node, delta in update.items():
                if node == "__interrupt__":
                    interrupts = delta if isinstance(delta, list) else [delta]
                    for itr in interrupts:
                        question = (getattr(itr, "value", {}) or {}).get(
                            "question", "Please clarify your question."
                        )
                        yield _format_event(SSEEvent(type="interrupt", question=question))
                    return

                # Emit node_start for EVERY invocation, including loopbacks —
                # each visit is a separate phase the UI timeline should render
                # as its own pill (attempt 1, attempt 2, …).
                yield _format_event(SSEEvent(type="node_start", node=node))

                payload_delta = _filter_delta(delta) if isinstance(delta, dict) else {}
                yield _format_event(
                    SSEEvent(type="node_end", node=node, state_delta=payload_delta)
                )

                # If synthesis just produced the final answer, emit it explicitly.
                if node == "synthesis" and isinstance(delta, dict) and delta.get("final_answer"):
                    yield _format_event(
                        SSEEvent(type="final_message", content=delta["final_answer"])
                    )

            # Periodic keepalive so reverse-proxy idle timeouts don't kill the stream.
            await asyncio.sleep(0)

    except asyncio.CancelledError:
        logger.info("Client disconnected mid-stream for thread %s", thread_id)
        raise
    except Exception as exc:
        logger.exception("Graph stream failed for thread %s", thread_id)
        yield _format_event(SSEEvent(type="error", message=f"{type(exc).__name__}: {exc}"))


async def get_history(thread_id: str) -> ThreadHistory:
    """Reconstruct the conversation from the checkpointed state.

    Must be async because the checkpointer may be ``AsyncPostgresSaver``
    (when ``DATABASE_URL`` is set), which doesn't allow sync calls from
    the main thread.
    """
    graph = get_graph()
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = await graph.aget_state(config)

    if not snapshot.values:
        raise HTTPException(status_code=404, detail="thread not found")

    msgs: list[MessageSnapshot] = []
    for m in snapshot.values.get("messages", []) or []:
        if isinstance(m, HumanMessage):
            msgs.append(MessageSnapshot(role="user", content=m.content))
        elif isinstance(m, AIMessage):
            msgs.append(
                MessageSnapshot(role="assistant", content=m.content, name=m.name)
            )
        else:
            msgs.append(MessageSnapshot(role="system", content=str(m.content)))

    interrupted = bool(snapshot.next)
    pending_question = None
    if interrupted:
        pending_question = snapshot.values.get("clarification_question")

    return ThreadHistory(
        thread_id=thread_id,
        messages=msgs,
        interrupted=interrupted,
        pending_question=pending_question,
    )


async def is_thread_awaiting_resume(thread_id: str) -> bool:
    """Async because ``aget_state`` is the only safe call on
    ``AsyncPostgresSaver`` from the FastAPI event loop."""
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = await get_graph().aget_state(config)
    return bool(snapshot.values) and bool(snapshot.next)
