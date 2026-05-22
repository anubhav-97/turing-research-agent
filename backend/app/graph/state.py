"""State schema for the research-assistant graph.

The TypedDict is LangGraph's idiomatic state container. ``messages`` uses the
``add_messages`` reducer so multi-turn history accumulates automatically across
thread checkpoints; every other field is overwritten by the latest node return.
"""

from __future__ import annotations

from typing import Annotated, Literal, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

ClarityStatus = Literal["clear", "needs_clarification", "unknown"]
ValidationResult = Literal["sufficient", "insufficient", "unknown"]
ResearchSource = Literal["mock", "tavily", "stub"]


class ResearchFinding(TypedDict, total=False):
    """A single research result. ``total=False`` so partial dicts are allowed."""

    company: str
    recent_news: str
    stock_info: str
    key_developments: str
    source: ResearchSource
    raw_notes: str  # free-form planning notes from the DeepAgent


class ResearchState(TypedDict, total=False):
    # --- conversation history (multi-turn memory) ---
    messages: Annotated[list[BaseMessage], add_messages]

    # --- current turn ---
    user_query: str

    # --- Clarity Agent output ---
    company_name: str | None
    clarity_status: ClarityStatus
    clarification_question: str | None

    # --- Research Agent output ---
    research_findings: ResearchFinding | None
    confidence_score: int  # 0-10
    attempts: int  # number of research attempts so far

    # --- Validator Agent output ---
    validation_result: ValidationResult
    validation_feedback: str | None

    # --- Synthesis output ---
    final_answer: str | None


def initial_state(user_query: str) -> ResearchState:
    """Seed a fresh turn. ``messages`` is left empty here; the runtime appends
    the new HumanMessage so the checkpointed history is preserved."""
    return {
        "user_query": user_query,
        "company_name": None,
        "clarity_status": "unknown",
        "clarification_question": None,
        "research_findings": None,
        "confidence_score": 0,
        "attempts": 0,
        "validation_result": "unknown",
        "validation_feedback": None,
        "final_answer": None,
    }
