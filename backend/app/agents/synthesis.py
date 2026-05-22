"""Synthesis Agent — turns raw findings into a user-friendly final answer.

Consumes the full conversation history (multi-turn context) so follow-ups
can reference earlier turns naturally ("As I mentioned about Tesla earlier,
…"). Outputs Markdown for rendering in the frontend.
"""

from __future__ import annotations

import logging

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.graph.state import ResearchState

from .base import AgentBase, primary_llm

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are the Synthesis Agent. Your single job: answer
the user's SPECIFIC question using the research findings. You are not
writing a general profile of the company.

Inputs:
- The user's exact question (treat this as the brief — answer it directly).
- Curated baseline data: short summaries on news, stock, key developments.
- Research notes: free-form text, may include live web search results
  addressing a follow-up gap the validator flagged. **This often contains
  the most important fresh data — read it carefully and prefer it over
  the curated baseline when they conflict or when it answers the
  question more directly.**
- Prior conversation messages, for multi-turn context.

Output discipline:
1. **Lead with the direct answer** in 1-2 sentences. No "Here is what
   I know about X" preambles.
2. Follow with 2-4 supporting bullets, each citing the source inline:
   "(per curated data)" / "(per live web search)".
3. If the validator hit the 3-attempt cap and findings are still thin,
   open with: *"Some details may be incomplete — here's what's available:"*
4. **Never invent specifics** (names, dates, numbers) not in the inputs.
   If the user asked "who is the CEO" and there is no CEO info, say
   "I don't have current leadership data" — don't guess.
5. Reference prior turns naturally when the question is a follow-up
   ("Building on the Tesla overview earlier, ...").

Length: 80-180 words. Concise > comprehensive. The dev inspector shows
raw findings to power users — don't pad with redundancy."""


class SynthesisAgent(AgentBase):
    name = "synthesis"

    def __init__(self) -> None:
        self._llm = primary_llm()

    def __call__(self, state: ResearchState) -> dict:
        findings = state.get("research_findings") or {}
        history = state.get("messages", [])
        user_query = state["user_query"]
        attempts = state.get("attempts", 0)
        max_attempts_hit = (
            attempts >= 3 and state.get("validation_result") == "insufficient"
        )

        # Render BOTH the structured curated baseline AND the raw notes —
        # raw_notes often contains the live Tavily output that addresses
        # the validator's loopback feedback (the actual answer to the
        # user's specific question). Without including raw_notes the
        # synthesis LLM only sees the generic mock data.
        raw_notes = (findings.get("raw_notes") or "").strip()
        source = findings.get("source", "unknown")

        findings_blob_parts = [
            f"Company: {findings.get('company', 'unknown')}",
            f"Source: {source}  (cite as "
            + ("'per live web search'" if source == "tavily" else "'per curated data'")
            + ")",
            "",
            "Curated baseline:",
            f"- Recent news: {findings.get('recent_news', '(none)')}",
            f"- Stock info: {findings.get('stock_info', '(none)')}",
            f"- Key developments: {findings.get('key_developments', '(none)')}",
        ]
        if raw_notes and raw_notes not in {"(see notes)", findings.get("recent_news")}:
            findings_blob_parts += [
                "",
                "Research notes (may include live search results addressing the user's specific question):",
                raw_notes[:1800],
            ]
        findings_blob = "\n".join(findings_blob_parts)

        caveat = (
            "\n\nNote: The validator flagged gaps but we hit the 3-attempt "
            "cap; mention this limitation briefly in your answer.\n"
            if max_attempts_hit
            else ""
        )

        prompt = [
            SystemMessage(content=_SYSTEM_PROMPT),
            *history,
            HumanMessage(
                content=(
                    f"User question: {user_query}\n\nFindings:\n{findings_blob}{caveat}\n"
                    "Write the final Markdown answer."
                )
            ),
        ]

        try:
            response = self._llm.invoke(prompt)
            answer = response.content if hasattr(response, "content") else str(response)
        except Exception as exc:
            logger.exception("Synthesis failed")
            answer = _emergency_fallback(findings, user_query, exc)

        logger.info("Synthesis -> %d chars", len(answer))

        return {
            "final_answer": answer,
            "messages": [AIMessage(content=answer, name="synthesis_agent")],
        }


def _emergency_fallback(findings: dict, user_query: str, exc: Exception) -> str:
    """Format a presentable Markdown answer directly from findings when the
    Synthesis LLM call fails (e.g. Groq rate limit). We still want the user
    to get the research data — just without LLM polish.
    """
    company = findings.get("company") or "the company"
    source_label = (
        "per live web search"
        if findings.get("source") == "tavily"
        else "per curated data"
    )

    # If we have a Tavily blob, show a short excerpt — that's usually the
    # actual answer to the user's specific question.
    raw_notes = (findings.get("raw_notes") or "").strip()
    excerpt = ""
    if raw_notes and raw_notes not in {"(see notes)", findings.get("recent_news", "")}:
        excerpt_lines = [ln for ln in raw_notes.splitlines() if ln.strip()][:6]
        joined = "\n".join(excerpt_lines)[:600]
        excerpt = f"\n\n**Research excerpt** ({source_label}):\n\n```\n{joined}\n```"

    is_rate_limit = "rate" in str(exc).lower() or "429" in str(exc)
    banner = (
        "_Note: hit the daily token cap on the LLM that writes summaries. "
        "Showing raw research data instead — pipeline (Clarity → Research → "
        "Validator → Synthesis) ran to completion._"
        if is_rate_limit
        else "_Note: the summary step failed; here are the raw findings._"
    )

    return (
        f"{banner}\n\n"
        f"### {company}\n\n"
        f"- **Recent news** ({source_label}): {findings.get('recent_news', '(no data)')}\n"
        f"- **Stock info** ({source_label}): {findings.get('stock_info', '(no data)')}\n"
        f"- **Key developments** ({source_label}): {findings.get('key_developments', '(no data)')}\n"
        f"{excerpt}"
    )
