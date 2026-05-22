"""End-to-end graph tests with mocked agent nodes.

We replace the 4 agent classes with stub callables so we can exercise the
graph topology (routing + interrupt + checkpoint) without hitting Groq.

The graph itself is real LangGraph — only the agents are stubbed.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from app.graph.builder import build_graph

# --- Stub agents that mimic real return shapes ------------------------------

class _ClarityStub:
    """Cycles through scripted responses, one per call."""

    def __init__(self, responses: list[dict[str, Any]]):
        self.responses = list(responses)
        self.calls = 0

    def __call__(self, state):
        idx = min(self.calls, len(self.responses) - 1)
        self.calls += 1
        return self.responses[idx]


class _ResearchStub:
    def __init__(self, confidences: list[int]):
        self.confidences = list(confidences)
        self.calls = 0

    def __call__(self, state):
        idx = min(self.calls, len(self.confidences) - 1)
        confidence = self.confidences[idx]
        self.calls += 1
        return {
            "research_findings": {
                "company": state.get("company_name") or "Test Co",
                "recent_news": "stub news",
                "stock_info": "stub stock",
                "key_developments": "stub devs",
                "source": "mock",
                "raw_notes": f"attempt {self.calls}",
            },
            "confidence_score": confidence,
            "attempts": state.get("attempts", 0) + 1,
        }


class _ValidatorStub:
    def __init__(self, verdicts: list[str]):
        self.verdicts = list(verdicts)
        self.calls = 0

    def __call__(self, state):
        idx = min(self.calls, len(self.verdicts) - 1)
        verdict = self.verdicts[idx]
        self.calls += 1
        return {
            "validation_result": verdict,
            "validation_feedback": "stub feedback",
        }


class _SynthesisStub:
    def __call__(self, state):
        return {"final_answer": "## stub answer", "messages": []}


# --- Fixtures ---------------------------------------------------------------

@pytest.fixture
def build_with_stubs(monkeypatch):
    """Patch the 4 agent classes the builder imports, then compile a graph."""

    def _build(clarity_responses, research_confidences, validator_verdicts):
        clarity_stub = _ClarityStub(clarity_responses)
        research_stub = _ResearchStub(research_confidences)
        validator_stub = _ValidatorStub(validator_verdicts)
        synthesis_stub = _SynthesisStub()

        with patch("app.graph.builder.ClarityAgent", return_value=clarity_stub), \
             patch("app.graph.builder.ResearchAgent", return_value=research_stub), \
             patch("app.graph.builder.ValidatorAgent", return_value=validator_stub), \
             patch("app.graph.builder.SynthesisAgent", return_value=synthesis_stub):
            graph = build_graph(checkpointer=MemorySaver())
        return graph, {
            "clarity": clarity_stub,
            "research": research_stub,
            "validator": validator_stub,
        }

    return _build


# --- The 3 scenarios from the spec -----------------------------------------

def test_happy_path_high_confidence_skips_validator(build_with_stubs):
    """clear -> research (confidence=8) -> synthesis (validator skipped)."""
    graph, stubs = build_with_stubs(
        clarity_responses=[{"clarity_status": "clear", "company_name": "Apple Inc."}],
        research_confidences=[8],
        validator_verdicts=["sufficient"],
    )
    config = {"configurable": {"thread_id": "t-happy"}}
    result = graph.invoke(
        {
            "user_query": "Tell me about Apple",
            "messages": [HumanMessage(content="Tell me about Apple")],
        },
        config=config,
    )
    assert result["final_answer"] == "## stub answer"
    assert stubs["validator"].calls == 0, "validator should be skipped on high confidence"
    assert stubs["research"].calls == 1


def test_loopback_low_confidence_then_validator_loops(build_with_stubs):
    """research(c=3) -> validator(insufficient) -> research(c=8) -> synthesis."""
    graph, stubs = build_with_stubs(
        clarity_responses=[{"clarity_status": "clear", "company_name": "Tesla"}],
        research_confidences=[3, 8],
        validator_verdicts=["insufficient", "sufficient"],
    )
    config = {"configurable": {"thread_id": "t-loop"}}
    result = graph.invoke(
        {"user_query": "Tesla stock", "messages": [HumanMessage(content="Tesla stock")]},
        config=config,
    )
    assert result["final_answer"] == "## stub answer"
    assert stubs["research"].calls == 2, "research should run twice"
    # On the 2nd research, confidence=8 -> validator skipped on second pass too
    assert stubs["validator"].calls == 1


def test_max_attempts_caps_loop_at_three(build_with_stubs):
    """Validator forever-insufficient -> research caps at attempts=3."""
    graph, stubs = build_with_stubs(
        clarity_responses=[{"clarity_status": "clear", "company_name": "Boeing"}],
        research_confidences=[1, 1, 1, 1, 1],
        validator_verdicts=["insufficient"] * 10,
    )
    config = {"configurable": {"thread_id": "t-cap"}}
    result = graph.invoke(
        {"user_query": "Boeing", "messages": [HumanMessage(content="Boeing")]},
        config=config,
    )
    assert result["final_answer"] == "## stub answer"
    assert stubs["research"].calls == 3, "research must not exceed 3 attempts"


def test_interrupt_pauses_then_resumes(build_with_stubs):
    """Unclear query -> interrupt -> resume with clarification -> proceed."""
    graph, stubs = build_with_stubs(
        clarity_responses=[
            {
                "clarity_status": "needs_clarification",
                "company_name": None,
                "clarification_question": "Which company?",
            },
            {"clarity_status": "clear", "company_name": "Tesla"},
        ],
        research_confidences=[8],
        validator_verdicts=["sufficient"],
    )
    config = {"configurable": {"thread_id": "t-interrupt"}}

    # Turn 1: graph runs until interrupt
    pre = graph.invoke(
        {
            "user_query": "Tell me about that EV company",
            "messages": [HumanMessage(content="Tell me about that EV company")],
        },
        config=config,
    )
    # The state at this point should reflect the interrupt
    assert "__interrupt__" in pre or pre.get("clarity_status") == "needs_clarification"

    # Resume with the user's clarification
    resumed = graph.invoke(Command(resume="Tesla"), config=config)
    assert resumed["final_answer"] == "## stub answer"
    # Clarity ran twice: once before interrupt, once after resume
    assert stubs["clarity"].calls == 2
