"""Compose the agents into the executable LangGraph.

Topology::

    START -> clarity -> [clarification (interrupt) | research]
    clarification -> clarity            # after Command(resume=...)
    research -> [validator | synthesis]
    validator -> [research | synthesis]
    synthesis -> END

The checkpointer is chosen by :mod:`app.graph.checkpointer` — Postgres
(Supabase or anything else) when ``DATABASE_URL`` is set, otherwise an
in-memory ``MemorySaver``. Tests may pass an explicit override.
"""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.agents import ClarityAgent, ResearchAgent, SynthesisAgent, ValidatorAgent

from .checkpointer import get_checkpointer
from .routing import route_after_clarity, route_after_research, route_after_validator
from .state import ResearchState

logger = logging.getLogger(__name__)

# Module-level cached graph. Populated eagerly by the FastAPI startup
# handler (which can `await make_async_checkpointer()`), so subsequent
# requests reuse the same compiled graph + async pool.
_graph = None


def _clarification_node(state: ResearchState) -> dict:
    """Pause execution and wait for a human reply.

    ``interrupt()`` raises a GraphInterrupt that propagates up; the caller
    resumes via ``graph.invoke(Command(resume=user_reply), config)``. The
    returned value becomes ``human_reply`` below, which we append to the
    conversation history and stash as the new ``user_query`` so the next
    Clarity pass sees the disambiguation.
    """
    question = state.get("clarification_question") or "Could you clarify your question?"
    human_reply = interrupt({"question": question})

    return {
        "user_query": str(human_reply),
        "messages": [HumanMessage(content=str(human_reply))],
        # Reset clarity decision so the next Clarity pass re-evaluates fresh.
        "clarity_status": "unknown",
        "clarification_question": None,
    }


def build_graph(checkpointer: BaseCheckpointSaver | None = None):
    """Construct and compile the research-assistant graph.

    Args:
        checkpointer: Optional override (handy for tests that want a fresh
            saver). When omitted, uses :func:`get_checkpointer` which
            selects Postgres or MemorySaver based on ``DATABASE_URL``.
    """
    clarity = ClarityAgent()
    research = ResearchAgent()
    validator = ValidatorAgent()
    synthesis = SynthesisAgent()

    graph = StateGraph(ResearchState)

    graph.add_node("clarity", clarity)
    graph.add_node("clarification", _clarification_node)
    graph.add_node("research", research)
    graph.add_node("validator", validator)
    graph.add_node("synthesis", synthesis)

    graph.add_edge(START, "clarity")
    graph.add_conditional_edges(
        "clarity",
        route_after_clarity,
        {"clarification": "clarification", "research": "research"},
    )
    # After the human replies, re-evaluate clarity. This handles the case
    # where the user's reply itself is still vague.
    graph.add_edge("clarification", "clarity")

    graph.add_conditional_edges(
        "research",
        route_after_research,
        {"validator": "validator", "synthesis": "synthesis"},
    )
    graph.add_conditional_edges(
        "validator",
        route_after_validator,
        {"research": "research", "synthesis": "synthesis"},
    )
    graph.add_edge("synthesis", END)

    compiled = graph.compile(checkpointer=checkpointer or get_checkpointer())
    logger.info("Graph compiled with %d nodes", len(compiled.nodes))
    return compiled


def set_graph(graph) -> None:
    """Register a pre-built graph (called from FastAPI startup after the
    async checkpointer is ready). Subsequent ``get_graph()`` calls return
    this instance instead of building lazily."""
    global _graph
    _graph = graph


def get_graph():
    """Return the singleton graph.

    If FastAPI startup already injected one via :func:`set_graph`, return
    it. Otherwise build lazily with the sync ``get_checkpointer()`` — the
    CLI demo and pytest use this fallback path.
    """
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph
