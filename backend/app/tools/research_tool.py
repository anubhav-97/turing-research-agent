"""Research tools wired up as LangChain tools for the Research DeepAgent.

Two tools are exposed:

1. ``lookup_mock_company`` — instant case-insensitive lookup against the
   curated mock dataset. Always returns deterministic content, ideal for
   reviewers running offline.
2. ``tavily_search`` — live web search via Tavily when ``TAVILY_API_KEY`` is
   set. The DeepAgent picks this when the mock lookup doesn't fit (e.g. an
   uncommon company or a follow-up that needs fresher data).

Both tools return structured dicts; the agent decides how to combine them.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import tool

from app.config import get_settings
from app.data.mock_companies import lookup

logger = logging.getLogger(__name__)


@tool
def lookup_mock_company(company: str) -> dict[str, Any]:
    """Look up a company in the curated mock-research dataset.

    Use this FIRST for well-known public companies (Apple, Tesla, NVIDIA,
    Microsoft, Google, Amazon and common aliases like AAPL or alphabet).
    Returns ``{"found": false}`` when the company isn't covered.

    Args:
        company: Company name or ticker (case-insensitive).
    """
    hit = lookup(company)
    if hit is None:
        return {"found": False, "company": company}
    return {
        "found": True,
        "source": "mock",
        **hit,
    }


@tool
def tavily_search(query: str) -> dict[str, Any]:
    """Search the live web via Tavily.

    Use this when ``lookup_mock_company`` returned ``found: false``, or when
    the user explicitly asks for fresh / recent information not covered by
    the mock dataset.

    Args:
        query: A focused natural-language query, e.g.
            "Tesla Q3 2025 earnings highlights" — NOT a single keyword.
    """
    settings = get_settings()
    if not settings.tavily_enabled:
        return {
            "found": False,
            "reason": "TAVILY_API_KEY not configured on the server",
            "source": "stub",
        }
    try:
        from tavily import TavilyClient
    except ImportError:
        logger.warning("tavily-python not installed; returning stub")
        return {"found": False, "reason": "tavily client not installed", "source": "stub"}

    try:
        client = TavilyClient(api_key=settings.tavily_api_key)
        result = client.search(query=query, max_results=5, search_depth="advanced")
        return {
            "found": True,
            "source": "tavily",
            "query": query,
            "answer": result.get("answer"),
            "results": [
                {
                    "title": r.get("title"),
                    "url": r.get("url"),
                    "content": r.get("content", "")[:500],
                }
                for r in result.get("results", [])
            ],
        }
    except Exception as exc:
        logger.warning("Tavily search failed: %s", exc)
        return {"found": False, "reason": f"tavily error: {exc}", "source": "stub"}


RESEARCH_TOOLS = [lookup_mock_company, tavily_search]
