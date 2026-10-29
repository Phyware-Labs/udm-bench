"""Placeholders for the UDM-MCP conditions C-G.

The paper evaluates five conditions over the unified data model, served to the
agent through a UDM-over-MCP server: C (full tool surface), D (no cross-source
correlation), E (no compliance audit), F (schema introspection only) and G (no
``health_scan``). Their implementations are not part of this repository; the
scored outputs of every run are (``scoring_results_*``), so every number in the
paper can still be recomputed. See the README, "What is not included".

They stay registered so ``--condition C`` fails with an explanation rather than
"unknown condition".
"""

from __future__ import annotations

from typing import Any

from harness.backends.base import ToolCall
from harness.conditions.base import Condition, ToolResult
from harness.conditions.registry import register_condition


class ConditionNotIncluded(RuntimeError):
    """Raised when a condition that is not shipped in this repository is used."""


class UnavailableCondition(Condition):
    """A registered condition whose implementation is not included."""

    def __init__(self, code: str, name: str, description: str) -> None:
        self.code = code
        self.name = name
        self.description = description
        super().__init__()

    def _fail(self) -> ConditionNotIncluded:
        return ConditionNotIncluded(
            f"Condition {self.code} ({self.name}) is not included in the public "
            "udm-bench release. Its scored results are in scoring_results_*; see "
            "README.md, 'What is not included'."
        )

    def tool_specs(self) -> list[dict[str, Any]]:
        raise self._fail()

    def system_prompt(self) -> str:
        raise self._fail()

    def initial_user_message(self, *, mission_meta: dict[str, Any]) -> str:
        raise self._fail()

    def execute_tool(self, call: ToolCall, *, mission_dir: str) -> ToolResult:
        raise self._fail()


UNAVAILABLE: tuple[tuple[str, str, str], ...] = (
    ("C", "udm-mcp-full", "UDM over MCP with the full tool surface, including health_scan."),
    ("D", "udm-mcp-no-correlate", "C without cross-source correlation."),
    ("E", "udm-mcp-no-compliance", "C without the compliance audit."),
    ("F", "udm-mcp-introspection", "Schema introspection only."),
    ("G", "udm-mcp-no-healthscan", "C without the health_scan triage tool."),
)

for _code, _name, _desc in UNAVAILABLE:
    register_condition(UnavailableCondition(_code, _name, _desc))
