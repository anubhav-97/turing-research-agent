"""FastAPI application entry point."""

from __future__ import annotations

import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import router
from app.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    if settings.llm_provider == "groq" and not settings.groq_api_key:
        logger.warning("LLM_PROVIDER=groq but GROQ_API_KEY is empty")
    if settings.llm_provider == "anthropic" and not settings.anthropic_api_key:
        logger.warning("LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is empty")

    app = FastAPI(
        title="Turing Research Agent",
        version=__version__,
        description=(
            "Multi-agent research assistant — LangGraph + DeepAgents + Groq. "
            "Streams agent transitions as Server-Sent Events."
        ),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    app.include_router(router)

    @app.on_event("startup")
    async def _startup() -> None:  # pragma: no cover - side-effect only
        # Build the graph eagerly with an *async* checkpointer so
        # graph.astream() works (sync PostgresSaver doesn't implement
        # async methods). For MemorySaver mode, this is a no-op-ish init.
        from app.agents.base import active_models
        from app.graph.builder import build_graph, set_graph
        from app.graph.checkpointer import make_async_checkpointer

        checkpointer = await make_async_checkpointer()
        set_graph(build_graph(checkpointer=checkpointer))

        fast_m, primary_m = active_models()
        logger.info(
            "Backend started | version=%s | provider=%s | tavily=%s | persistence=%s | models=%s/%s",
            __version__,
            settings.llm_provider,
            "on" if settings.tavily_enabled else "off",
            "postgres" if settings.persistence_enabled else "in-memory",
            fast_m,
            primary_m,
        )

    @app.on_event("shutdown")
    async def _shutdown() -> None:  # pragma: no cover
        from app.graph.checkpointer import close_async_pool

        await close_async_pool()

    return app


app = create_app()
