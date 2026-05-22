"""Application settings — loaded from environment via pydantic-settings."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM provider ---
    # "groq" (free tier, llama models) or "anthropic" (paid, Claude models).
    # Flip via LLM_PROVIDER env var. Auto-falls back to whichever key is set
    # if both are configured; if both missing, startup logs a warning.
    llm_provider: Literal["groq", "anthropic"] = Field(default="groq")

    # --- LLM credentials ---
    groq_api_key: str = Field(default="", description="Groq API key")
    anthropic_api_key: str = Field(default="", description="Anthropic Claude API key")
    tavily_api_key: str = Field(default="", description="Optional Tavily key for live search")

    # --- Persistence ---
    # Postgres connection string for the LangGraph checkpointer. When set,
    # threads survive backend restarts. Works with any Postgres (Supabase,
    # Neon, Railway Postgres, RDS, self-hosted). Leave empty for the
    # zero-config MemorySaver fallback.
    #
    # Supabase: Project Settings → Database → "Connection string" → URI.
    # Use the Session Pooler (port 5432) or Direct Connection; the
    # Transaction Pooler (6543) breaks LangGraph's prepared statements.
    database_url: str = Field(default="", description="Postgres URL for persistent checkpoints")

    # --- Groq models (used when LLM_PROVIDER=groq) ---
    groq_model_primary: str = Field(
        default="llama-3.3-70b-versatile",
        description="Stronger model used by Research (DeepAgent) and Synthesis",
    )
    groq_model_fast: str = Field(
        default="llama-3.1-8b-instant",
        description="Faster model used by Clarity and Validator classifiers",
    )

    # --- Anthropic models (used when LLM_PROVIDER=anthropic) ---
    # Pinned to specific dated model IDs for reproducibility. Override via
    # env to track newer versions.
    anthropic_model_primary: str = Field(
        default="claude-sonnet-4-5-20250929",
        description="Stronger Claude model for Research + Synthesis",
    )
    anthropic_model_fast: str = Field(
        default="claude-haiku-4-5-20251001",
        description="Faster Claude model for Clarity + Validator classifiers",
    )

    # --- Server ---
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- Graph behaviour ---
    max_research_attempts: int = 3
    confidence_threshold: int = 6  # >= threshold => skip validator

    # --- Research agent harness ---
    # DeepAgents makes 5-6 LLM calls per Research turn carrying tool definitions
    # in every call. That's heavy for the Groq free tier (12k TPM). Default OFF;
    # ResearchAgent falls back to direct mock-tool lookup which is fast and
    # uses zero extra LLM tokens for the tool itself. Flip to true if you have
    # the headroom or want to demo the harness explicitly.
    enable_deepagent: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def tavily_enabled(self) -> bool:
        return bool(self.tavily_api_key)

    @property
    def persistence_enabled(self) -> bool:
        return bool(self.database_url)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
