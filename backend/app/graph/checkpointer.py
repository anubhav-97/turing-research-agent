"""Checkpointer factory — selects PostgresSaver (Supabase / any Postgres)
when ``DATABASE_URL`` is set, otherwise falls back to in-memory.

This is the single source of truth for graph persistence. Everything else
(graph builder, services, tests) just calls :func:`get_checkpointer()`
and never knows which backend is live.

Why a long-lived ``ConnectionPool`` instead of the documented
``PostgresSaver.from_conn_string(url) as cp:`` context manager: the
compiled graph is a module-level singleton spanning the full server
lifetime, so the pool must outlive any ``with`` block. We open it once
at import time and close it on process exit via ``atexit``.

Supabase notes:
- Use the *Session Pooler* (port 5432) or *Direct Connection* URL.
- The *Transaction Pooler* (port 6543) disables prepared statements,
  which LangGraph relies on — it'll appear to work but throw
  ``DuplicatePreparedStatement`` under any concurrency.
- ``setup()`` is idempotent — safe to call on every boot. It creates
  the ``checkpoints``, ``checkpoint_blobs``, and ``checkpoint_writes``
  tables in your default schema.
"""

from __future__ import annotations

import atexit
import logging
from functools import lru_cache

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver

from app.config import get_settings

logger = logging.getLogger(__name__)


# Connection-pool kwargs required for the LangGraph PostgresSaver protocol.
# autocommit=True : checkpoint writes must commit per call.
# prepare_threshold=0 : forces immediate preparation; required if the URL
#   targets a pooler in transaction mode.
_PSYCOPG_KWARGS = {"autocommit": True, "prepare_threshold": 0}


@lru_cache(maxsize=1)
def get_checkpointer() -> BaseCheckpointSaver:
    """Return the singleton checkpointer for this process.

    First call:
    - If ``DATABASE_URL`` is set, opens a psycopg connection pool, runs
      ``PostgresSaver.setup()`` (idempotent DDL), registers shutdown.
    - Otherwise returns a fresh ``MemorySaver`` (zero-config).

    Subsequent calls return the cached instance.
    """
    settings = get_settings()

    if not settings.persistence_enabled:
        logger.info("Checkpointer: MemorySaver (in-process, lost on restart)")
        return MemorySaver()

    try:
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg_pool import ConnectionPool
    except ImportError as exc:  # pragma: no cover - dependency missing
        logger.warning(
            "DATABASE_URL set but Postgres deps unavailable (%s); "
            "falling back to MemorySaver",
            exc,
        )
        return MemorySaver()

    try:
        pool = ConnectionPool(
            conninfo=settings.database_url,
            max_size=20,
            kwargs=_PSYCOPG_KWARGS,
            open=True,
        )
    except Exception as exc:
        logger.exception("Failed to open Postgres pool; falling back to MemorySaver")
        logger.warning("Postgres error: %s", exc)
        return MemorySaver()

    saver = PostgresSaver(pool)

    # PostgresSaver.setup() is *almost* idempotent — its CREATE TABLE
    # statements use IF NOT EXISTS, but its CREATE TYPE (for enum types
    # used internally) does NOT. So setup() succeeds the first time, then
    # raises UniqueViolation on every subsequent boot. We treat that
    # specific error as "already initialised" and continue. Any other
    # setup error is a real problem and falls back to MemorySaver.
    try:
        from psycopg.errors import DuplicateObject, UniqueViolation
    except ImportError:  # pragma: no cover - psycopg always installed if we got here
        DuplicateObject = UniqueViolation = ()  # type: ignore[assignment]

    try:
        saver.setup()
    except (DuplicateObject, UniqueViolation) as exc:
        logger.info(
            "PostgresSaver schema already initialised (%s); skipping setup",
            type(exc).__name__,
        )
    except Exception as exc:
        logger.exception("PostgresSaver.setup() failed; falling back to MemorySaver")
        logger.warning("Postgres setup error: %s", exc)
        pool.close()
        return MemorySaver()

    atexit.register(_safe_close, pool)
    logger.info(
        "Checkpointer: PostgresSaver (host=%s, pool=20) — threads will persist",
        _redact_host(settings.database_url),
    )
    return saver


def _safe_close(pool) -> None:
    try:
        pool.close()
    except Exception:  # pragma: no cover - shutdown best-effort
        pass


async def _safe_aclose(pool) -> None:
    try:
        await pool.close()
    except Exception:  # pragma: no cover
        pass


def _redact_host(url: str) -> str:
    """Pull just the host:port out of a Postgres URL for logging."""
    try:
        from urllib.parse import urlparse

        p = urlparse(url)
        return f"{p.hostname}:{p.port or 5432}"
    except Exception:  # pragma: no cover
        return "<unparseable>"


# Module-level holder for the async pool so the FastAPI shutdown event
# can close it cleanly. ``atexit`` can't await, so we register a sync
# closer here and the lifespan handler awaits the pool's close().
_async_pool = None


async def make_async_checkpointer() -> BaseCheckpointSaver:
    """Async factory — must be awaited from the FastAPI startup handler.

    Why a separate async factory: ``graph.astream()`` (used by the SSE
    endpoint) calls ``checkpointer.aget_tuple()`` etc. Sync ``PostgresSaver``
    raises NotImplementedError for those. We need ``AsyncPostgresSaver`` +
    ``AsyncConnectionPool``, and the pool's ``open()`` is an awaitable.
    """
    settings = get_settings()

    if not settings.persistence_enabled:
        logger.info("Checkpointer: MemorySaver (async-compatible)")
        return MemorySaver()

    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg_pool import AsyncConnectionPool
    except ImportError as exc:  # pragma: no cover
        logger.warning(
            "DATABASE_URL set but async Postgres deps unavailable (%s); "
            "falling back to MemorySaver",
            exc,
        )
        return MemorySaver()

    pool = AsyncConnectionPool(
        conninfo=settings.database_url,
        max_size=20,
        kwargs=_PSYCOPG_KWARGS,
        open=False,
    )
    try:
        await pool.open()
    except Exception as exc:
        logger.exception("Failed to open async Postgres pool; falling back to MemorySaver")
        logger.warning("Postgres error: %s", exc)
        return MemorySaver()

    saver = AsyncPostgresSaver(pool)

    try:
        from psycopg.errors import DuplicateObject, UniqueViolation
    except ImportError:  # pragma: no cover
        DuplicateObject = UniqueViolation = ()  # type: ignore[assignment]

    try:
        await saver.setup()
    except (DuplicateObject, UniqueViolation) as exc:
        logger.info(
            "AsyncPostgresSaver schema already initialised (%s); skipping setup",
            type(exc).__name__,
        )
    except Exception as exc:
        logger.exception("AsyncPostgresSaver.setup() failed; falling back to MemorySaver")
        logger.warning("Postgres setup error: %s", exc)
        await _safe_aclose(pool)
        return MemorySaver()

    global _async_pool
    _async_pool = pool
    logger.info(
        "Checkpointer: AsyncPostgresSaver (host=%s, pool=20) — threads will persist",
        _redact_host(settings.database_url),
    )
    return saver


async def close_async_pool() -> None:
    """Called by the FastAPI shutdown handler."""
    global _async_pool
    if _async_pool is not None:
        await _safe_aclose(_async_pool)
        _async_pool = None
