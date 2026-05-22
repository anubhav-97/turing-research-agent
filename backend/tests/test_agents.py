"""Agent contract tests — mock the Groq LLM so tests run offline.

We don't validate prompt content (brittle); we validate the *contract*:
given LLM output X, the agent returns state delta Y with the expected keys.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.agents.clarity import ClarityAgent, ClarityDecision
from app.agents.synthesis import SynthesisAgent
from app.agents.validator import ValidationVerdict, ValidatorAgent


@pytest.fixture
def stub_clarity_llm(monkeypatch):
    def factory(decision: ClarityDecision):
        mock = MagicMock()
        mock.with_structured_output = MagicMock(return_value=MagicMock(invoke=MagicMock(return_value=decision)))
        return mock

    return factory


def test_clarity_returns_clear_decision_unchanged():
    decision = ClarityDecision(
        clarity_status="clear",
        company_name="Tesla",
        clarification_question=None,
    )
    with patch("app.agents.clarity.fast_llm") as llm_factory:
        llm_factory.return_value.with_structured_output.return_value.invoke.return_value = decision
        agent = ClarityAgent()
        out = agent({"messages": [], "user_query": "What's up with Tesla?"})
    assert out["clarity_status"] == "clear"
    assert out["company_name"] == "Tesla"
    assert out["clarification_question"] is None


def test_clarity_handles_llm_failure_gracefully():
    """If the LLM throws, we should still produce a clarification-needed state."""
    with patch("app.agents.clarity.fast_llm") as llm_factory:
        llm_factory.return_value.with_structured_output.return_value.invoke.side_effect = RuntimeError("boom")
        agent = ClarityAgent()
        out = agent({"messages": [], "user_query": "x"})
    assert out["clarity_status"] == "needs_clarification"
    assert "company" in out["clarification_question"].lower()


def test_validator_returns_verdict_keys():
    verdict = ValidationVerdict(
        validation_result="insufficient",
        feedback="Need newer stock data",
    )
    with patch("app.agents.validator.fast_llm") as llm_factory:
        llm_factory.return_value.with_structured_output.return_value.invoke.return_value = verdict
        agent = ValidatorAgent()
        out = agent({"user_query": "stock?", "research_findings": {}})
    assert out["validation_result"] == "insufficient"
    assert out["validation_feedback"] == "Need newer stock data"


def test_validator_defaults_sufficient_on_llm_error():
    """If validator errors, we don't want to loop forever — default to sufficient."""
    with patch("app.agents.validator.fast_llm") as llm_factory:
        llm_factory.return_value.with_structured_output.return_value.invoke.side_effect = RuntimeError("boom")
        agent = ValidatorAgent()
        out = agent({"user_query": "stock?", "research_findings": {}})
    assert out["validation_result"] == "sufficient"
    assert "validator_error" in out["validation_feedback"]


def test_synthesis_produces_final_answer_and_message():
    fake_response = MagicMock()
    fake_response.content = "## Tesla\n- Cybertruck ramping up\n- Stock at $242"
    with patch("app.agents.synthesis.primary_llm") as llm_factory:
        llm_factory.return_value.invoke.return_value = fake_response
        agent = SynthesisAgent()
        out = agent(
            {
                "user_query": "Tell me about Tesla",
                "research_findings": {
                    "company": "Tesla",
                    "recent_news": "Cybertruck",
                    "stock_info": "$242",
                    "key_developments": "FSD v12",
                    "source": "mock",
                },
                "messages": [],
            }
        )
    assert out["final_answer"].startswith("## Tesla")
    assert len(out["messages"]) == 1
    assert out["messages"][0].name == "synthesis_agent"
