"""Clarity Agent — decides whether the user's query is specific enough.

Uses Groq with ``with_structured_output`` so the response is a Pydantic
object, not free-form text. That keeps the graph routing deterministic.

The agent is conversation-aware: if a prior turn already established a
company (e.g. "Tesla"), a follow-up like "What about their CEO?" is
considered ``clear`` because the company can be inferred from history.
"""

from __future__ import annotations

import logging
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.graph.state import ResearchState

from .base import AgentBase, fast_llm

logger = logging.getLogger(__name__)


class ClarityDecision(BaseModel):
    """Structured output schema for the Clarity Agent."""

    clarity_status: Literal["clear", "needs_clarification"] = Field(
        description=(
            "'clear' if the query specifies (or strongly implies from "
            "conversation history) a real company. 'needs_clarification' "
            "if the company is ambiguous, missing, or generic."
        )
    )
    company_name: str | None = Field(
        default=None,
        description=(
            "Canonical company name when clarity_status is 'clear'. "
            "Pull from prior turns if the new query is a follow-up. "
            "Leave null when clarification is needed."
        ),
    )
    clarification_question: str | None = Field(
        default=None,
        description=(
            "When clarity_status is 'needs_clarification', a single concise "
            "question asking the user to specify the company. Null otherwise."
        ),
    )


_SYSTEM_PROMPT = """You are the Clarity Agent in a research assistant pipeline.

Your job: determine whether the user's current query is specific enough to
research, or whether you must ask the user to clarify which company they
mean.

Rules:
- A query is CLEAR if it names a real, identifiable company (e.g. "Tesla",
  "AAPL", "the maker of Vision Pro") OR if a prior conversation turn already
  established the company and the new query is a follow-up (e.g. "What
  about their CEO?", "Tell me more about the stock").
- A query NEEDS CLARIFICATION when the company is missing, generic
  ("that EV company", "a tech firm"), or could refer to multiple companies.
- Pull the company name from the conversation history when it's a follow-up.
- Keep clarification questions short and direct ("Which company are you
  asking about?" rather than a paragraph)."""


class ClarityAgent(AgentBase):
    name = "clarity"

    def __init__(self) -> None:
        self._llm = fast_llm().with_structured_output(ClarityDecision)

    def __call__(self, state: ResearchState) -> dict:
        history = state.get("messages", [])
        user_query = state["user_query"]

        prompt_messages = [
            SystemMessage(content=_SYSTEM_PROMPT),
            *history,
            HumanMessage(
                content=(
                    f"Current user query: {user_query!r}\n\n"
                    "Decide clarity_status, extract company_name if possible, "
                    "and write clarification_question only when needed."
                )
            ),
        ]

        try:
            decision: ClarityDecision = self._llm.invoke(prompt_messages)
        except Exception as exc:
            logger.exception("Clarity agent failed")
            return {
                "clarity_status": "needs_clarification",
                "clarification_question": (
                    "Sorry, I had trouble understanding the request. "
                    "Could you tell me which company you'd like me to research?"
                ),
                "company_name": None,
                "_error": f"clarity_llm_error: {exc}",
            }

        logger.info(
            "Clarity -> status=%s company=%s",
            decision.clarity_status,
            decision.company_name,
        )

        return {
            "clarity_status": decision.clarity_status,
            "company_name": decision.company_name,
            "clarification_question": decision.clarification_question,
        }
