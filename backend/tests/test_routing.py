"""Exhaustive tests for the 3 conditional routing functions.

These are the spec's hard requirement — every branch must be covered.
"""

from __future__ import annotations

import pytest

from app.graph.routing import (
    route_after_clarity,
    route_after_research,
    route_after_validator,
)

# ---------- route_after_clarity ----------

@pytest.mark.parametrize(
    "clarity_status, expected",
    [
        ("needs_clarification", "clarification"),
        ("clear", "research"),
        ("unknown", "research"),  # default safe path
    ],
)
def test_route_after_clarity(clarity_status, expected):
    assert route_after_clarity({"clarity_status": clarity_status}) == expected


# ---------- route_after_research ----------

@pytest.mark.parametrize(
    "confidence, expected",
    [
        (0, "validator"),
        (5, "validator"),
        (6, "synthesis"),  # threshold edge
        (9, "synthesis"),
        (10, "synthesis"),
    ],
)
def test_route_after_research(confidence, expected):
    assert route_after_research({"confidence_score": confidence}) == expected


def test_route_after_research_missing_confidence_defaults_to_validator():
    """A missing score should NOT short-circuit to synthesis."""
    assert route_after_research({}) == "validator"


# ---------- route_after_validator ----------

@pytest.mark.parametrize(
    "validation, attempts, expected",
    [
        ("insufficient", 0, "research"),   # loop back
        ("insufficient", 1, "research"),
        ("insufficient", 2, "research"),
        ("insufficient", 3, "synthesis"),  # max hit -> stop looping
        ("insufficient", 4, "synthesis"),
        ("sufficient", 0, "synthesis"),    # done early
        ("sufficient", 2, "synthesis"),
        ("unknown", 1, "synthesis"),       # only insufficient triggers loopback
    ],
)
def test_route_after_validator(validation, attempts, expected):
    state = {"validation_result": validation, "attempts": attempts}
    assert route_after_validator(state) == expected
