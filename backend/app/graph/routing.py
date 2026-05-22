"""Conditional routing functions for the research-assistant graph.

These are pure functions taking ``ResearchState`` and returning the name of
the next node. Keeping them pure + side-effect-free makes them trivially
unit-testable across every branch, which is exactly what the spec asks for.
"""

from __future__ import annotations

from app.config import get_settings

from .state import ResearchState

_NODE_INTERRUPT = "clarification"
_NODE_RESEARCH = "research"
_NODE_VALIDATOR = "validator"
_NODE_SYNTHESIS = "synthesis"


def route_after_clarity(state: ResearchState) -> str:
    """After the Clarity Agent runs, decide whether to interrupt or proceed."""
    if state.get("clarity_status") == "needs_clarification":
        return _NODE_INTERRUPT
    return _NODE_RESEARCH


def route_after_research(state: ResearchState) -> str:
    """After Research, skip validation if confidence is already high enough."""
    threshold = get_settings().confidence_threshold
    if state.get("confidence_score", 0) >= threshold:
        return _NODE_SYNTHESIS
    return _NODE_VALIDATOR


def route_after_validator(state: ResearchState) -> str:
    """Loop back to Research if validation failed AND we have attempts left.

    The hard cap on ``attempts`` is enforced here (not by the LLM) so we
    never spin indefinitely.
    """
    max_attempts = get_settings().max_research_attempts
    if (
        state.get("validation_result") == "insufficient"
        and state.get("attempts", 0) < max_attempts
    ):
        return _NODE_RESEARCH
    return _NODE_SYNTHESIS
