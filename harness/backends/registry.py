"""Backend registry — map ``--model`` CLI strings to backend instances."""

from __future__ import annotations

from collections.abc import Callable

from harness.backends.base import Backend

_REGISTRY: dict[str, Callable[..., Backend]] = {}


def register_backend(model_id: str, factory: Callable[..., Backend]) -> None:
    """Register a backend factory under ``model_id``.

    Re-registration is allowed (helpful in tests) — the latest call wins.
    """
    _REGISTRY[model_id] = factory


def get_backend(model_id: str, **kwargs: object) -> Backend:
    """Instantiate the backend registered under ``model_id``.

    Raises ``KeyError`` if not registered.
    """
    if model_id not in _REGISTRY:
        raise KeyError(f"unknown model_id {model_id!r}; registered: {sorted(_REGISTRY)}")
    return _REGISTRY[model_id](**kwargs)


def registered_backends() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))
