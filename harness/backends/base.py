"""Common backend interface shared by all model providers."""

from __future__ import annotations

import abc
from dataclasses import asdict, dataclass, field
from typing import Any


class BackendError(RuntimeError):
    """Raised on unrecoverable backend failures (after retries)."""


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int
    completion_tokens: int
    usd_cost: float
    # Portion of ``prompt_tokens`` served from the provider's prompt cache (the
    # stable system-prompt / history prefix). Billed at the discounted cached
    # rate; recorded so cache-hit efficiency is measurable. Default 0 keeps
    # existing 3-arg constructors valid.
    cached_prompt_tokens: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ModelOutput:
    """One response from the model.

    ``tool_calls`` is the list of tool invocations the model wants to make
    on this turn. ``content`` is its natural-language response (typically
    empty when it's making tool calls).
    """

    content: str
    tool_calls: tuple[ToolCall, ...] = field(default_factory=tuple)
    stop_reason: str = "end_turn"
    usage: Usage = field(default_factory=lambda: Usage(0, 0, 0.0))
    latency_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "stop_reason": self.stop_reason,
            "usage": self.usage.to_dict(),
            "latency_ms": self.latency_ms,
        }


class Backend(abc.ABC):
    """Abstract base class for a pluggable model backend.

    Subclasses set :attr:`model_id` and implement :meth:`generate`. The
    framework records latency + token usage for every call so the harness
    can produce per-run cost reports.
    """

    #: Canonical model identifier (string used in the leaderboard).
    model_id: str = ""

    def __init__(self, *, temperature: float = 0.0, max_tokens: int = 4096) -> None:
        if not self.model_id:
            raise TypeError(f"{type(self).__name__} must set class attribute 'model_id'")
        self.temperature = temperature
        self.max_tokens = max_tokens

    @abc.abstractmethod
    def generate(
        self,
        *,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ModelOutput:
        """Produce one model turn (text + tool-calls + usage)."""
