"""Research Agent — the only agent built on the DeepAgents harness.

DeepAgents is overkill for classifier-style agents, but research IS
open-ended: the agent may want to look up a known company in the mock
dataset, fall back to Tavily for unknowns or fresher data, and reason over
the validator's feedback when looping back. Giving it a built-in planning
tool (``write_todos``) plus our two search tools is a natural fit.

After the deep agent finishes, we ask the primary LLM to assign a 0-10
confidence score against the user's original query — this drives the
``route_after_research`` branch.
"""

from __future__ import annotations

import logging
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.config import get_settings
from app.graph.state import ResearchFinding, ResearchState
from app.tools.research_tool import RESEARCH_TOOLS, lookup_mock_company

from .base import AgentBase, fast_llm, primary_llm

logger = logging.getLogger(__name__)


_RESEARCH_INSTRUCTIONS = """You are the Research Agent in a multi-agent research assistant.

Goal: gather concrete, recent, factual information about a specific company
to answer the user's question.

Workflow:
1. ALWAYS start with ``lookup_mock_company`` for the company name — it's
   curated, fast, and authoritative for well-known firms.
2. If ``lookup_mock_company`` returns ``found: false``, OR the user's
   question asks for very recent / niche details not in the mock, call
   ``tavily_search`` with a focused natural-language query.
3. If the validator previously marked your output insufficient, you'll see
   their feedback in the conversation. Use it to choose a different angle:
   maybe a more specific search query, or combining both tools.
4. Produce a final concise summary covering: recent news, stock/financials,
   key developments. Cite the source (mock vs tavily) inline.

Do not editorialise. Do not invent facts. If a tool returns nothing useful,
say so plainly — the validator will decide what to do."""


class ConfidenceJudgement(BaseModel):
    """LLM-assigned self-evaluation of how well the findings answer the query."""

    confidence: int = Field(
        ge=0,
        le=10,
        description=(
            "0 = no useful info; 5 = partial; 10 = comprehensive answer to "
            "the user's specific question."
        ),
    )
    rationale: str = Field(description="Brief justification (1 sentence).")


_CONFIDENCE_PROMPT = """You rate how well research findings answer the
user's SPECIFIC question, on a 0-10 scale. Be a strict judge — low scores
trigger validation that improves the final answer.

Anchors (use these literally; do not drift toward 7-8 by default):
  0  : findings contain nothing about the company.
  1-3: findings cover the company in general but DO NOT address the
       specific thing the user asked about (e.g. user asked about CEO
       but findings only mention products / stock / news).
  4-5: findings partially address the question — some relevant facts
       but missing important specifics (dates, names, numbers).
  6-7: findings address the question with most of the relevant facts.
  8-9: findings comprehensively answer with specifics.
  10 : a polished answer is directly extractable from the findings.

Cardinal rule: if the user's question asks for a SPECIFIC FACT
(a person's name, a date, a number, a recent event) and that fact is
not in the findings, the score must be ≤ 3 regardless of how much
other content is present. Do not award credit for tangentially-related
information."""


class ResearchAgent(AgentBase):
    name = "research"

    def __init__(self) -> None:
        self._llm = primary_llm()
        # Use the *fast* model for scoring — it's a cheap classification,
        # 8b is plenty, and saves the 70b TPM budget for synthesis.
        self._confidence_llm = fast_llm().with_structured_output(ConfidenceJudgement)
        self._deep_agent = self._build_deep_agent()

    def _build_deep_agent(self):
        """Build the DeepAgents harness lazily so import is cheap in tests.

        Disabled by default (``ENABLE_DEEPAGENT=false``) because the harness
        spends ~5-6 LLM calls per turn — too heavy for Groq free tier (12k TPM).
        Set ``ENABLE_DEEPAGENT=true`` to opt in.
        """
        if not get_settings().enable_deepagent:
            logger.info("DeepAgent harness disabled via ENABLE_DEEPAGENT; using direct tool fallback")
            return None

        try:
            from deepagents import create_deep_agent
        except ImportError as exc:  # pragma: no cover - env issue
            logger.warning("deepagents not available (%s); falling back to plain ReAct", exc)
            return None

        try:
            return create_deep_agent(
                tools=RESEARCH_TOOLS,
                instructions=_RESEARCH_INSTRUCTIONS,
                model=self._llm,
            )
        except Exception as exc:
            logger.warning("create_deep_agent failed (%s); falling back to direct tool call", exc)
            return None

    def __call__(self, state: ResearchState) -> dict:
        company = state.get("company_name") or "the user's referenced company"
        user_query = state["user_query"]
        validator_feedback = state.get("validation_feedback")
        attempts = state.get("attempts", 0) + 1

        # Build the prompt for the deep agent, including validator hints if any.
        prompt_parts = [f"Company: {company}", f"User question: {user_query}"]
        if validator_feedback:
            prompt_parts.append(
                f"Previous research was judged INSUFFICIENT for: {validator_feedback}. "
                "Address this gap specifically."
            )
        agent_input = "\n".join(prompt_parts)

        findings_text, source = self._run_deep_agent_or_fallback(
            company, agent_input, user_query, validator_feedback
        )

        # Normalise into a ResearchFinding dict. The deep agent's free-form
        # text is preserved in raw_notes; the structured fields come from a
        # direct mock lookup when available, otherwise we keep the prose.
        mock_hit = lookup_mock_company.invoke({"company": company})
        if mock_hit.get("found") and source != "tavily":
            finding: ResearchFinding = {
                "company": mock_hit.get("company", company),
                "recent_news": mock_hit["recent_news"],
                "stock_info": mock_hit["stock_info"],
                "key_developments": mock_hit["key_developments"],
                "source": "mock",
                "raw_notes": findings_text,
            }
        elif mock_hit.get("found") and source == "tavily":
            # We augmented mock with Tavily: merge so structured fields stay,
            # but mark source so the UI / synthesis cite live search.
            finding = {
                "company": mock_hit.get("company", company),
                "recent_news": mock_hit["recent_news"],
                "stock_info": mock_hit["stock_info"],
                "key_developments": mock_hit["key_developments"],
                "source": "tavily",
                "raw_notes": findings_text,
            }
        else:
            finding = {
                "company": company,
                "recent_news": findings_text[:500],
                "stock_info": "(see notes)",
                "key_developments": "(see notes)",
                "source": source,
                "raw_notes": findings_text,
            }

        confidence = self._score_confidence(user_query, findings_text)

        logger.info(
            "Research -> attempt=%d confidence=%d source=%s",
            attempts,
            confidence,
            finding["source"],
        )

        return {
            "research_findings": finding,
            "confidence_score": confidence,
            "attempts": attempts,
            "messages": [
                AIMessage(
                    content=f"[research/attempt-{attempts}] {findings_text}",
                    name="research_agent",
                )
            ],
        }

    def _run_deep_agent_or_fallback(
        self,
        company: str,
        agent_input: str,
        user_query: str,
        validator_feedback: str | None,
    ) -> tuple[str, Literal["mock", "tavily", "stub"]]:
        """Execute the DeepAgent if available; otherwise call tools directly.

        Behaviour:
        - DeepAgent path (when enabled): the agent picks tools itself.
        - Fallback path:
          1. If validator gave feedback AND Tavily is on → run Tavily with a
             feedback-driven query. This is the "informed loop" — the validator's
             words literally shape the next search. Augments mock data.
          2. Else if company is in the mock → return curated entry.
          3. Else if Tavily is on → run a generic Tavily search.
          4. Else → stub.
        """
        if self._deep_agent is not None:
            try:
                result = self._deep_agent.invoke(
                    {"messages": [HumanMessage(content=agent_input)]}
                )
                msgs = result.get("messages", [])
                if msgs:
                    last = msgs[-1]
                    return getattr(last, "content", str(last)) or "", "mock"
            except Exception as exc:
                logger.warning("DeepAgent invoke failed (%s); falling back", exc)

        settings = get_settings()
        mock_hit = lookup_mock_company.invoke({"company": company})

        # Informed loop: validator gave specific feedback → use it as the
        # Tavily search query, augmenting the mock when present.
        if validator_feedback and settings.tavily_enabled:
            from app.tools.research_tool import tavily_search

            query = f"{company} {validator_feedback}".strip()
            logger.info("Loopback retry → tavily_search(query=%r)", query[:120])
            t = tavily_search.invoke({"query": query})
            if t.get("found"):
                tavily_text = str(t.get("answer") or t.get("results"))
                if mock_hit.get("found"):
                    blob = (
                        f"--- curated baseline ---\n"
                        f"Recent news: {mock_hit['recent_news']}\n"
                        f"Stock info: {mock_hit['stock_info']}\n"
                        f"Key developments: {mock_hit['key_developments']}\n\n"
                        f"--- live search (addressing validator feedback) ---\n"
                        f"{tavily_text[:1500]}"
                    )
                else:
                    blob = tavily_text[:1500]
                return blob, "tavily"

        # No feedback (first attempt) or Tavily unavailable: prefer mock.
        if mock_hit.get("found"):
            blob = (
                f"Recent news: {mock_hit['recent_news']}\n"
                f"Stock info: {mock_hit['stock_info']}\n"
                f"Key developments: {mock_hit['key_developments']}\n"
                f"(source: mock)"
            )
            return blob, "mock"

        # Last resort: try Tavily once with a generic query.
        if settings.tavily_enabled:
            from app.tools.research_tool import tavily_search

            t = tavily_search.invoke({"query": f"{company} {user_query}"})
            if t.get("found"):
                return str(t.get("answer") or t.get("results"))[:1500], "tavily"

        return f"No findings available for {company!r}.", "stub"

    def _score_confidence(self, user_query: str, findings_text: str) -> int:
        prompt = [
            SystemMessage(content=_CONFIDENCE_PROMPT),
            HumanMessage(
                content=(
                    f"User question: {user_query}\n\nFindings:\n{findings_text}\n\n"
                    "Give a 0-10 confidence + one-sentence rationale."
                )
            ),
        ]
        try:
            judgement: ConfidenceJudgement = self._confidence_llm.invoke(prompt)
            return judgement.confidence
        except Exception as exc:
            logger.warning("Confidence scoring failed (%s); defaulting to 3", exc)
            return 3
