"""HTTP routes — thin SSE wrappers around ``chat_service``."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.api.schemas import ChatRequest, ResumeRequest, ThreadHistory
from app.services import chat_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/chat")
async def chat(req: ChatRequest):
    """Run a new turn on a thread; stream SSE events to the client."""
    stream = chat_service.stream_graph(thread_id=req.thread_id, user_message=req.message)
    return EventSourceResponse(stream)


@router.post("/chat/resume")
async def chat_resume(req: ResumeRequest):
    """Resume an interrupted thread with the user's clarification."""
    if not await chat_service.is_thread_awaiting_resume(req.thread_id):
        raise HTTPException(
            status_code=409, detail="thread not awaiting clarification"
        )
    stream = chat_service.stream_graph(
        thread_id=req.thread_id, user_message=None, resume_value=req.clarification
    )
    return EventSourceResponse(stream)


@router.get("/threads/{thread_id}", response_model=ThreadHistory)
async def get_thread(thread_id: str) -> ThreadHistory:
    """Return the full checkpointed history for a thread (for page refresh)."""
    return await chat_service.get_history(thread_id)
