"""Deterministic in-process backend used by tests and dry-runs.

The mock backend returns a scripted sequence of :class:`ModelOutput`
responses. Token usage is reported as deterministic functions of the
prompt/response length so harness-level accounting can be unit-tested.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from harness.backends.base import Backend, BackendError, ModelOutput, Usage
from harness.backends.registry import register_backend


class MockBackend(Backend):
    model_id = "mock"

    def __init__(
        self,
        *,
        responses: Iterable[ModelOutput] | None = None,
        usd_per_run: float = 0.0,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._responses = list(responses or [])
        self._idx = 0
        self.usd_per_run = usd_per_run
        self.calls: list[dict[str, Any]] = []

    def generate(
        self,
        *,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ModelOutput:
        self.calls.append(
            {"system_prompt": system_prompt, "messages": list(messages), "tools": list(tools)}
        )
        if self._idx >= len(self._responses):
            raise BackendError(
                f"MockBackend exhausted (scripted={len(self._responses)} calls, "
                f"requested={self._idx + 1})"
            )
        resp = self._responses[self._idx]
        self._idx += 1
        # Attach a deterministic usage estimate if none was provided.
        if resp.usage == Usage(0, 0, 0.0):
            prompt_tokens = sum(len(m.get("content", "")) for m in messages) // 4
            completion_tokens = (len(resp.content) // 4) + 16 * len(resp.tool_calls)
            resp = ModelOutput(
                content=resp.content,
                tool_calls=resp.tool_calls,
                stop_reason=resp.stop_reason,
                usage=Usage(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    usd_cost=self.usd_per_run / max(len(self._responses), 1),
                ),
                latency_ms=resp.latency_ms or 1,
            )
        return resp


def _factory(**kwargs: object) -> MockBackend:
    return MockBackend(**kwargs)


register_backend("mock", _factory)
