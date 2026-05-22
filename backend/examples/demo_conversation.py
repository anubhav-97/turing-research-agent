"""End-to-end demo: two example turns from the spec, run against the real graph.

Turn 1: vague query  -> Clarity interrupts -> user supplies "Tesla" -> graph
        resumes -> Research -> Synthesis -> answer
Turn 2: follow-up    -> Clarity sees Tesla in history -> Research -> maybe
        Validator loopback -> Synthesis -> answer

Both turns share a thread_id so the MemorySaver preserves history.

Requires a real ``GROQ_API_KEY`` in the environment (or ``.env`` next to
this file's ``../``). Tavily is optional.

Usage:
    cd backend
    python -m examples.demo_conversation
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.types import Command

# Load .env (key in backend/.env) so this works without manual `export`.
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass

from app.graph.builder import build_graph

# ANSI for readability
_CYAN = "\033[36m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def _banner(title: str) -> None:
    line = "═" * (len(title) + 4)
    print(f"\n{_BOLD}{_CYAN}╔{line}╗\n║  {title}  ║\n╚{line}╝{_RESET}")


def _print_node_trace(stream) -> dict[str, Any] | None:
    """Consume an update stream, print one line per node, return final state."""
    last_state = None
    for update in stream:
        for node, delta in update.items():
            if node == "__interrupt__":
                # The interrupt payload is a list of Interrupt objects
                interrupts = delta if isinstance(delta, list) else [delta]
                for itr in interrupts:
                    question = (getattr(itr, "value", {}) or {}).get(
                        "question", "(clarification needed)"
                    )
                    print(
                        f"{_YELLOW}  ↪ INTERRUPT: {question!r}{_RESET}"
                    )
                continue
            tag = f"{_GREEN}✓{_RESET}"
            highlights = []
            if isinstance(delta, dict):
                if "clarity_status" in delta:
                    highlights.append(f"clarity={delta['clarity_status']}")
                if delta.get("company_name"):
                    highlights.append(f"company={delta['company_name']}")
                if "confidence_score" in delta:
                    highlights.append(f"conf={delta['confidence_score']}")
                if "attempts" in delta:
                    highlights.append(f"att={delta['attempts']}")
                if "validation_result" in delta:
                    highlights.append(f"valid={delta['validation_result']}")
            hl = (" " + _DIM + " · ".join(highlights) + _RESET) if highlights else ""
            print(f"  {tag} {_BOLD}{node:<14}{_RESET}{hl}")
            last_state = delta
    return last_state


def run_turn(graph, thread_id: str, user_message: str, resume_with: str | None = None) -> dict[str, Any]:
    """Run one turn. If resume_with is set, we're resuming an interrupted thread."""
    config = {"configurable": {"thread_id": thread_id}}

    if resume_with is None:
        print(f"\n{_BOLD}USER:{_RESET} {user_message}")
        payload = {
            "user_query": user_message,
            "messages": [HumanMessage(content=user_message)],
        }
        stream = graph.stream(payload, config=config, stream_mode="updates")
    else:
        print(f"\n{_BOLD}USER (clarification):{_RESET} {resume_with}")
        stream = graph.stream(Command(resume=resume_with), config=config, stream_mode="updates")

    _print_node_trace(stream)

    # Check whether the graph is paused at an interrupt
    snapshot = graph.get_state(config)
    return {
        "final_state": snapshot.values,
        "interrupted": bool(snapshot.next),
        "next": snapshot.next,
    }


def main() -> int:
    if not os.environ.get("GROQ_API_KEY"):
        print(
            "ERROR: GROQ_API_KEY is not set. Get a free key from "
            "https://console.groq.com/keys and either export it or put it in backend/.env",
            file=sys.stderr,
        )
        return 1

    _banner("LangGraph Research Assistant — Demo")
    print(f"{_DIM}Model: Groq | Tavily: "
          f"{'on' if os.environ.get('TAVILY_API_KEY') else 'off (mock only)'}{_RESET}")

    graph = build_graph()
    thread_id = f"demo-{uuid.uuid4().hex[:8]}"
    print(f"{_DIM}thread_id={thread_id}{_RESET}")

    # === Turn 1: vague query that triggers a clarification interrupt ===
    _banner("Turn 1 — vague query triggers interrupt")
    state = run_turn(graph, thread_id, "Tell me about that EV company")
    if state["interrupted"]:
        state = run_turn(graph, thread_id, "", resume_with="Tesla")
    final = state["final_state"].get("final_answer", "(no answer)")
    print(f"\n{_BOLD}ASSISTANT:{_RESET}\n{final}\n")

    # === Turn 2: follow-up that exercises multi-turn memory ===
    _banner("Turn 2 — follow-up uses prior context")
    state = run_turn(graph, thread_id, "What about their recent stock performance?")
    if state["interrupted"]:
        state = run_turn(graph, thread_id, "", resume_with="Tesla")
    final = state["final_state"].get("final_answer", "(no answer)")
    print(f"\n{_BOLD}ASSISTANT:{_RESET}\n{final}\n")

    _banner("Demo complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
