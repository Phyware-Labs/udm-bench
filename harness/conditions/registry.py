"""Registry mapping condition codes (A–F) to instances."""

from __future__ import annotations

from harness.conditions.base import Condition

_REGISTRY: dict[str, Condition] = {}


def register_condition(condition: Condition) -> None:
    _REGISTRY[condition.code.upper()] = condition


def get_condition(code: str) -> Condition:
    key = code.upper()
    if key not in _REGISTRY:
        raise KeyError(f"unknown condition {code!r}; registered: {sorted(_REGISTRY)}")
    return _REGISTRY[key]


def registered_conditions() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))
