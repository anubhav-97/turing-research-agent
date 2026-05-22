"""Agent implementations. Each agent is a callable: ``state -> partial_state``."""

from .clarity import ClarityAgent
from .research import ResearchAgent
from .synthesis import SynthesisAgent
from .validator import ValidatorAgent

__all__ = ["ClarityAgent", "ResearchAgent", "SynthesisAgent", "ValidatorAgent"]
