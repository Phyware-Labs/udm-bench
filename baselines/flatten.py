"""Flatten a decoded message's nested ``fields`` dict into scalar columns.

Used by both the SQL converter (one column per leaf) and the text renderer.
Nested message dicts are joined with ``sep`` (default ``__``); arrays/lists are
serialized to JSON so they survive into a single SQL cell.
"""

from __future__ import annotations

import json
from typing import Any

Scalar = Any


def flatten_scalars(fields: dict[str, Any], *, sep: str = "__") -> dict[str, Scalar]:
    """Flatten ``fields`` to ``{column_name: scalar_or_json_string}``.

    * nested dicts -> recursed, keys joined with ``sep``
    * lists / tuples -> JSON string (kept queryable, e.g. ``LIKE`` matches)
    * scalars (int/float/str/bool/None) -> unchanged
    """
    out: dict[str, Scalar] = {}

    def _walk(prefix: str, value: Any) -> None:
        if isinstance(value, dict):
            for k, v in value.items():
                _walk(f"{prefix}{sep}{k}" if prefix else str(k), v)
        elif isinstance(value, (list, tuple)):
            out[prefix] = json.dumps(_jsonable(value))
        else:
            out[prefix] = value

    _walk("", fields)
    return out


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value
