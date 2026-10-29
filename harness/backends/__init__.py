"""Pluggable model backends for the udm-bench harness.

Every backend conforms to :class:`harness.backends.base.Backend` and registers
itself with :mod:`harness.backends.registry`. This repository ships the
deterministic in-process :mod:`harness.backends.mock` backend used by the tests;
to run against a hosted model, implement ``Backend`` for your provider and call
:func:`register_backend` (see ``harness/README.md``).
"""

from harness.backends.base import Backend, BackendError, ModelOutput, ToolCall, Usage
from harness.backends.mock import MockBackend
from harness.backends.registry import get_backend, register_backend, registered_backends

__all__ = [
    "Backend",
    "BackendError",
    "MockBackend",
    "ModelOutput",
    "ToolCall",
    "Usage",
    "get_backend",
    "register_backend",
    "registered_backends",
]
