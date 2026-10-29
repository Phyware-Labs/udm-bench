"""Backend registry + mock backend tests."""

from __future__ import annotations

import pytest

from harness.backends import (
    BackendError,
    ModelOutput,
    ToolCall,
    Usage,
    get_backend,
    register_backend,
    registered_backends,
)
from harness.backends.mock import MockBackend


def test_mock_backend_returns_scripted_responses():
    responses = [
        ModelOutput(content="hello", tool_calls=()),
        ModelOutput(content="world", tool_calls=(ToolCall(name="foo", arguments={}),)),
    ]
    b = MockBackend(responses=responses, usd_per_run=0.10)
    out1 = b.generate(system_prompt="sys", messages=[{"role": "user", "content": "hi"}], tools=[])
    out2 = b.generate(system_prompt="sys", messages=[{"role": "user", "content": "ok"}], tools=[])
    assert out1.content == "hello"
    assert out2.tool_calls[0].name == "foo"
    # Synthetic usage is filled in.
    assert out1.usage.completion_tokens > 0


def test_mock_backend_raises_when_exhausted():
    b = MockBackend(responses=[ModelOutput(content="x")])
    b.generate(system_prompt="", messages=[], tools=[])
    with pytest.raises(BackendError, match="exhausted"):
        b.generate(system_prompt="", messages=[], tools=[])


def test_registry_round_trip():
    register_backend("test-only", lambda **kw: MockBackend(responses=[ModelOutput(content="ok")]))
    assert "test-only" in registered_backends()
    inst = get_backend("test-only")
    assert isinstance(inst, MockBackend)


def test_registry_unknown_raises():
    with pytest.raises(KeyError, match="unknown model_id"):
        get_backend("nope-no-such-backend")


def test_usage_dataclass_to_dict():
    u = Usage(prompt_tokens=1, completion_tokens=2, usd_cost=3.0)
    assert u.to_dict() == {
        "prompt_tokens": 1,
        "completion_tokens": 2,
        "usd_cost": 3.0,
        "cached_prompt_tokens": 0,
    }


def test_tool_call_dataclass_to_dict():
    tc = ToolCall(name="foo", arguments={"x": 1})
    assert tc.to_dict() == {"name": "foo", "arguments": {"x": 1}}
