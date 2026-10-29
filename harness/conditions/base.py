"""Abstract base class for a harness condition.

A condition encapsulates:

1. **The tool surface** the model is given for this run.
2. **The execution loop**: given a model output's tool calls, dispatch them
   against the right backing data store (raw bag, SQL, UDM-MCP) and feed
   results back to the model on the next turn.
3. **The "answer" extractor**: pull the structured diagnosis from the
   model's final natural-language reply.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any

from harness.backends.base import ToolCall


@dataclass(frozen=True)
class ToolResult:
    name: str
    content: str  # JSON-encoded string for backends that expect text payloads
    is_error: bool = False


class Condition(abc.ABC):
    """Abstract base for an experimental condition plugin."""

    code: str = ""  # "A", "B", "C", "D", "E", "F"
    name: str = ""
    description: str = ""

    def __init__(self) -> None:
        if not self.code or not self.name:
            raise TypeError(f"{type(self).__name__} must set class attributes 'code' and 'name'")

    @abc.abstractmethod
    def tool_specs(self) -> list[dict[str, Any]]:
        """Return the JSON-Schema tool definitions exposed to the model."""

    @abc.abstractmethod
    def system_prompt(self) -> str:
        """The system prompt used for this condition."""

    @abc.abstractmethod
    def initial_user_message(self, *, mission_meta: dict[str, Any]) -> str:
        """The first user-turn message bootstrapping the diagnosis task."""

    def orientation_preamble(self, *, mission_dir: str, mission_meta: dict[str, Any]) -> str | None:
        """Optional harness-issued orientation block for the first user message.

        Conditions that can cheaply enumerate their backing store (e.g. UDM-MCP)
        may override this to hand the agent a topology summary — which sources
        exist, how many events each has, and the mission time window — so the
        model does not burn turns guessing source ids / event types. The block
        is deterministic and costs the agent no model turn. ``None`` (the
        default) means no preamble is appended.
        """
        return None

    @abc.abstractmethod
    def execute_tool(self, call: ToolCall, *, mission_dir: str) -> ToolResult:
        """Execute one tool call against this condition's backing data store."""
