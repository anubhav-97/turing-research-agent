"""Tests for the state schema and initial-state seeding."""

from __future__ import annotations

from app.graph.state import initial_state


def test_initial_state_has_expected_defaults():
    s = initial_state("Tell me about Tesla")

    assert s["user_query"] == "Tell me about Tesla"
    assert s["clarity_status"] == "unknown"
    assert s["confidence_score"] == 0
    assert s["attempts"] == 0
    assert s["validation_result"] == "unknown"
    assert s["final_answer"] is None
    assert s["company_name"] is None


def test_initial_state_keeps_query_verbatim():
    """No transformation should happen to the raw user input."""
    weird = "  Tell me about  Tesla???  "
    assert initial_state(weird)["user_query"] == weird
