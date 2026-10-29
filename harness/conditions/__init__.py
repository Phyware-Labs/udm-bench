"""Experimental conditions (PhyWare UDM-Bench).

Each condition module registers itself with :mod:`harness.conditions.registry`
so the harness CLI can resolve ``--condition A`` (etc.) to a plugin instance.

This repository ships the two baselines, A (raw bag text) and B (generic SQL).
The UDM-MCP conditions C-G are registered as placeholders that explain they are
not included; see :mod:`harness.conditions.unavailable` and the README.
"""

from harness.conditions import (  # noqa: F401
    a_raw_bag,
    b_sql,
    unavailable,
)
from harness.conditions.base import Condition
from harness.conditions.registry import get_condition, register_condition, registered_conditions

__all__ = [
    "Condition",
    "get_condition",
    "register_condition",
    "registered_conditions",
]
