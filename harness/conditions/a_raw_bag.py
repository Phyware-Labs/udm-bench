"""Condition A — raw native data as text.

The agent is given decoded ROS2 bag text (TurtleBot3) and/or PX4 logs as
plain text dumps via a single ``read_bag_text`` tool. No structure beyond
what the raw bag provides.
"""

from __future__ import annotations

import json
import os
from typing import Any

from baselines.prepare import parse_bag_dirname
from harness.backends.base import ToolCall
from harness.conditions._diagnosis import submit_diagnosis_tool
from harness.conditions.base import Condition, ToolResult
from harness.conditions.registry import register_condition
from harness.prompts import load_system_prompt

# Hard caps so a single read can never blow the model's context window. The bag
# text can be tens of MB; the agent pages through it with start_line.
_MAX_LINES_CAP = 1000
_MAX_CHARS = 40_000


class RawBagCondition(Condition):
    code = "A"
    name = "raw-bag-text"
    description = "Decoded bag text per platform; no structured query surface."

    def tool_specs(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "list_sources",
                "description": (
                    "List the telemetry sources available for this mission as "
                    "(vendor, source_id) pairs. Call this first to discover which "
                    "source_ids to pass to read_bag_text."
                ),
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "read_bag_text",
                "description": (
                    "Return a window of the decoded text dump of a ROS2 bag (TurtleBot3) "
                    "or PX4 ULog. The dump is chronological, one message per line. The "
                    "file can be very large, so reads are paginated: pass start_line to "
                    "seek and max_lines for the window size (capped). The response begins "
                    "with a JSON header giving total_lines and next_start_line so you can "
                    "page through. Use vendor/source_id from list_sources."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "vendor": {"type": "string", "enum": ["turtlebot3", "px4"]},
                        "source_id": {"type": "string"},
                        "start_line": {"type": "integer", "default": 0},
                        "max_lines": {"type": "integer", "default": 200},
                    },
                    "required": ["vendor", "source_id"],
                },
            },
            submit_diagnosis_tool(),
        ]

    def system_prompt(self) -> str:
        return load_system_prompt(self.code)

    def initial_user_message(self, *, mission_meta: dict[str, Any]) -> str:
        return (
            f"Mission {mission_meta.get('mission_id')} just completed.\n"
            f"Composition: {mission_meta.get('composition')}\n"
            f"Vendors involved: {mission_meta.get('vendors')}\n"
            f"World: {mission_meta.get('world')}\n\n"
            "Call list_sources to see the available telemetry sources, then "
            "diagnose any fault that occurred during this mission."
        )

    def execute_tool(self, call: ToolCall, *, mission_dir: str) -> ToolResult:
        if call.name == "list_sources":
            return ToolResult(name=call.name, content=json.dumps(self._list_sources(mission_dir)))
        if call.name == "read_bag_text":
            vendor = str(call.arguments.get("vendor", ""))
            source_id = str(call.arguments.get("source_id", ""))
            start_line = max(int(call.arguments.get("start_line", 0)), 0)
            max_lines = min(int(call.arguments.get("max_lines", 200)), _MAX_LINES_CAP)
            path = os.path.join(mission_dir, f"bag_{vendor}_{source_id}.txt")
            if not os.path.exists(path):
                return ToolResult(
                    name=call.name,
                    content=json.dumps(
                        {
                            "error": f"no bag text for {vendor}/{source_id}",
                            "available": self._list_sources(mission_dir),
                        }
                    ),
                    is_error=True,
                )
            with open(path, encoding="utf-8") as f:
                all_lines = f.readlines()
            total = len(all_lines)
            window = all_lines[start_line : start_line + max_lines]
            text = "".join(window)
            truncated_chars = None
            if len(text) > _MAX_CHARS:
                text = text[:_MAX_CHARS]
                truncated_chars = _MAX_CHARS
            end_line = start_line + len(window)
            header = {
                "total_lines": total,
                "start_line": start_line,
                "returned_lines": len(window),
                "next_start_line": end_line if end_line < total else None,
                "truncated_to_chars": truncated_chars,
            }
            return ToolResult(name=call.name, content=json.dumps(header) + "\n" + text)
        if call.name == "submit_diagnosis":
            return ToolResult(name=call.name, content=json.dumps({"received": True}))
        return ToolResult(
            name=call.name,
            content=json.dumps({"error": f"unknown tool {call.name!r}"}),
            is_error=True,
        )

    @staticmethod
    def _list_sources(mission_dir: str) -> list[dict[str, str]]:
        """Discover available ``(vendor, source_id)`` pairs from bag text dumps."""
        sources: list[dict[str, str]] = []
        try:
            names = sorted(os.listdir(mission_dir))
        except OSError:
            return sources
        for name in names:
            if not name.startswith("bag_") or not name.endswith(".txt"):
                continue
            parsed = parse_bag_dirname(name[: -len(".txt")])
            if parsed is not None:
                vendor, source_id = parsed
                sources.append({"vendor": vendor, "source_id": source_id})
        return sources


register_condition(RawBagCondition())
