"""Shared agent infrastructure: provider-aware LLM factories + a tiny base class.

Two model tiers, abstracted across providers:

* ``fast_llm()`` — small fast model for Clarity & Validator (cheap JSON
  classifiers). Groq: ``llama-3.1-8b-instant`` / Anthropic: Haiku.
* ``primary_llm()`` — stronger model for Research planning & Synthesis
  (open-ended generation). Groq: ``llama-3.3-70b-versatile`` / Anthropic:
  Sonnet.

Provider is selected via ``LLM_PROVIDER`` env var (``groq`` | ``anthropic``).
Both factories return objects implementing the LangChain ``Runnable`` /
chat-model interface, so downstream agent code is provider-agnostic.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from langchain_core.language_models.chat_models import BaseChatModel

from app.config import get_settings

logger = logging.getLogger(__name__)


def _build_chat_model(*, primary: bool) -> BaseChatModel:
    """Construct the chat model for the configured provider + tier."""
    s = get_settings()
    temperature = 0.2 if primary else 0.0

    if s.llm_provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        model = s.anthropic_model_primary if primary else s.anthropic_model_fast
        if not s.anthropic_api_key:
            logger.warning(
                "LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set — "
                "calls will fail at the LLM boundary"
            )
        return ChatAnthropic(
            model=model,
            api_key=s.anthropic_api_key,
            temperature=temperature,
            max_retries=1,
            max_tokens=1024 if primary else 512,
        )

    # Default: Groq
    from langchain_groq import ChatGroq

    model = s.groq_model_primary if primary else s.groq_model_fast
    if not s.groq_api_key:
        logger.warning(
            "LLM_PROVIDER=groq but GROQ_API_KEY is not set — "
            "calls will fail at the LLM boundary"
        )
    return ChatGroq(
        model=model,
        api_key=s.groq_api_key,
        temperature=temperature,
        max_retries=1,
    )


@lru_cache(maxsize=1)
def fast_llm() -> BaseChatModel:
    return _build_chat_model(primary=False)


@lru_cache(maxsize=1)
def primary_llm() -> BaseChatModel:
    return _build_chat_model(primary=True)


def active_models() -> tuple[str, str]:
    """Return ``(fast_model_name, primary_model_name)`` for logging."""
    s = get_settings()
    if s.llm_provider == "anthropic":
        return s.anthropic_model_fast, s.anthropic_model_primary
    return s.groq_model_fast, s.groq_model_primary


class AgentBase:
    """Marker base class. Subclasses implement ``__call__(state)``."""

    name: str = "agent"

    def __call__(self, state):  # pragma: no cover - interface only
        raise NotImplementedError
