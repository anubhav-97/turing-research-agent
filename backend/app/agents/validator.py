"""Validator Agent — judges whether the Research findings answer the query.

Reliability features baked in:

1. **Contradiction guard** (`_resolve_contradictions`): when the LLM says
   ``sufficient`` but the feedback contains negation language ("no info",
   "missing", "could not find"), we flip the verdict to ``insufficient``.
   Small models occasionally generate this kind of self-contradicting JSON;
   trusting the verdict alone leads to bad answers being marked OK.
2. **Few-shot prompt**: 3 concrete examples bias the model toward consistent
   verdicts.
3. **Confidence-anchored**: receives the Research agent's confidence score
   as a prior so it doesn't independently re-judge the same thing.
4. **Safe default on LLM error**: returns `sufficient` to avoid infinite loops
   (the attempt-cap in routing is the safety net).
"""

from __future__ import annotations

import logging
import re
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.graph.state import ResearchState

from .base import AgentBase, fast_llm

logger = logging.getLogger(__name__)


# Strong-signal phrases that imply the findings are NOT sufficient.
# Kept narrow on purpose — the original wider regex (including "search for"
# / "look up") false-positives on legitimate positive feedback like
# "good coverage; no further search needed". The patterns below appear
# almost exclusively when the LLM is describing a real gap.
_NEGATION_PHRASES = re.compile(
    r"\b("
    r"no (?:information|info|data|mention|details|coverage|reference)|"
    r"missing|"
    r"could not (?:find|locate|determine)|"
    r"does not (?:include|mention|contain|cover|address)|"
    r"doesn'?t (?:include|mention|contain|cover|address)|"
    r"not enough|"
    r"insufficient|"
    r"unable to (?:find|determine|answer)|"
    r"needs? (?:more|fresher|recent|specific)|"
    r"requires? more|"
    r"lacks?"
    r")\b",
    re.IGNORECASE,
)

# Hedge phrases that should INHIBIT the contradiction flip even if a
# negation phrase appears nearby. Example: "no further info needed" or
# "missing nothing important" — these are positive.
_POSITIVE_HEDGE = re.compile(
    r"\b("
    r"no (?:further|additional|more) (?:info|information|search|details)|"
    r"missing nothing|"
    r"covers? (?:enough|sufficiently|the question)"
    r")\b",
    re.IGNORECASE,
)


class ValidationVerdict(BaseModel):
    """Structured output from the Validator Agent."""

    validation_result: Literal["sufficient", "insufficient"] = Field(
        description=(
            "'sufficient' if the findings answer the user's specific "
            "question well; 'insufficient' if they're vague, off-topic, "
            "outdated, or missing key facts the user asked for."
        )
    )
    feedback: str = Field(
        min_length=3,
        description=(
            "When insufficient, a one-sentence directive telling the next "
            "Research pass exactly what's missing (e.g. 'no information on "
            "recent CEO; search for current Tesla leadership'). When "
            "sufficient, a brief confirmation of why."
        ),
    )


_SYSTEM_PROMPT = """You are the Validator Agent. You judge whether research
findings answer the user's specific question.

CRITICAL RULES:
1. The `validation_result` and `feedback` fields MUST be consistent.
   - If you set `sufficient`, the feedback MUST be a positive confirmation
     (e.g. "findings cover stock and key developments adequately").
   - If you find ANY concrete gap, you MUST set `insufficient` AND describe
     the gap in feedback ("no information on X; search for Y").
   - NEVER pair `sufficient` with feedback that mentions missing info, gaps,
     or what to search for. That is a contradiction.

2. Feedback for insufficient cases must be ACTIONABLE — a directive that can
   literally be used as the next search query. Bad: "needs more info". Good:
   "no information on current CEO; search 'Apple Tim Cook tenure'".

3. Prefer `sufficient` for roughly on-topic, marginally incomplete findings —
   avoid hairsplitting that loops the graph.

EXAMPLES

User question: "Tell me about Apple"
Findings: Cover recent news, stock price, AI integration.
→ {"validation_result": "sufficient", "feedback": "findings cover news, stock, and AI strategy adequately"}

User question: "Who is the CEO of Apple?"
Findings: Vision Pro launch, stock at $195, AI integration. No leadership info.
→ {"validation_result": "insufficient", "feedback": "no information on current CEO; search 'current Apple CEO Tim Cook'"}

User question: "What were Tesla's Q3 2025 earnings?"
Findings: Cybertruck ramping up, FSD v12 rollout, stock at $242 volatile quarter.
→ {"validation_result": "insufficient", "feedback": "no Q3 2025 earnings figures; search 'Tesla Q3 2025 earnings report revenue'"}
"""


class ValidatorAgent(AgentBase):
    name = "validator"

    def __init__(self) -> None:
        self._llm = fast_llm().with_structured_output(ValidationVerdict)

    def __call__(self, state: ResearchState) -> dict:
        findings = state.get("research_findings") or {}
        user_query = state["user_query"]
        confidence = state.get("confidence_score", 0)
        attempts = state.get("attempts", 0)

        findings_blob = (
            f"Company: {findings.get('company', 'unknown')}\n"
            f"Recent news: {findings.get('recent_news', '(none)')}\n"
            f"Stock info: {findings.get('stock_info', '(none)')}\n"
            f"Key developments: {findings.get('key_developments', '(none)')}\n"
            f"Source: {findings.get('source', 'unknown')}\n"
            f"Notes: {findings.get('raw_notes', '')[:600]}\n"
            f"Self-rated confidence (by Research): {confidence}/10\n"
            f"Attempt #: {attempts}"
        )

        prompt = [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    f"User question: {user_query}\n\nResearch findings:\n{findings_blob}\n\n"
                    "Return validation_result + feedback. Remember: NEVER pair "
                    "'sufficient' with feedback that describes a gap."
                )
            ),
        ]

        try:
            verdict: ValidationVerdict = self._llm.invoke(prompt)
        except Exception as exc:
            logger.exception("Validator failed; defaulting to sufficient")
            return {
                "validation_result": "sufficient",
                "validation_feedback": f"validator_error: {exc}; defaulted to sufficient",
            }

        # Reliability guard: catch the "sufficient + negation in feedback"
        # contradiction the small model occasionally produces.
        result, feedback = _resolve_contradictions(
            verdict.validation_result, verdict.feedback
        )

        logger.info(
            "Validator -> %s%s (%s)",
            result,
            " [contradiction-flip]" if result != verdict.validation_result else "",
            feedback[:80],
        )
        return {
            "validation_result": result,
            "validation_feedback": feedback,
        }


def _resolve_contradictions(
    result: Literal["sufficient", "insufficient"], feedback: str
) -> tuple[Literal["sufficient", "insufficient"], str]:
    """If the LLM said 'sufficient' but the feedback documents a real gap,
    flip to 'insufficient'. Returns the (possibly corrected) pair.

    Positive-hedge phrases (e.g. "no further info needed") inhibit the
    flip — they LOOK like negation but are actually positive."""
    if result != "sufficient":
        return result, feedback

    if not _NEGATION_PHRASES.search(feedback):
        return result, feedback

    # Negation phrase found — but check if it's actually a positive hedge.
    if _POSITIVE_HEDGE.search(feedback):
        return result, feedback

    logger.warning(
        "Validator contradiction: sufficient + negation in feedback (%r) — flipping to insufficient",
        feedback[:100],
    )
    return "insufficient", feedback
