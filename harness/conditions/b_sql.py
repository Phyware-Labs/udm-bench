"""Condition B — generic SQL over per-topic tables for each vendor.

The agent is given a single ``query_sql`` tool against a SQLite database
that contains one table per recorded topic per vendor. The vendor-native
schema is preserved; the agent has to bridge vendor terminology itself.
"""

from __future__ import annotations

import json
import os
import sqlite3
from typing import Any

from harness.backends.base import ToolCall
from harness.conditions._diagnosis import submit_diagnosis_tool
from harness.conditions.base import Condition, ToolResult
from harness.conditions.registry import register_condition
from harness.prompts import load_system_prompt

# Max characters a single query result may contribute to the conversation. Wide
# or array-valued tables (costmaps, NaN-flooded telemetry) can return 200 rows
# that still total hundreds of KB; without a cap the accumulated tool results
# overflow the model's context window over a multi-call run. Oversized results
# are truncated (fewer rows) with an explicit notice so the agent can narrow its
# query (project columns, add WHERE) instead of the run crashing.
_MAX_RESULT_CHARS = 60_000


class SqlCondition(Condition):
    code = "B"
    name = "generic-sql"
    description = "SQLite per-topic tables per vendor; vendor-native schema preserved."

    def tool_specs(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "list_tables",
                "description": "List all SQL tables (one per recorded topic per vendor).",
                "input_schema": {"type": "object", "properties": {}},
            },
            {
                "name": "describe_table",
                "description": "Return the column names and types for a table.",
                "input_schema": {
                    "type": "object",
                    "properties": {"table": {"type": "string"}},
                    "required": ["table"],
                },
            },
            {
                "name": "query_sql",
                "description": (
                    "Run a read-only SQL query against the mission's telemetry "
                    "database. SELECT only — INSERT/UPDATE/DELETE/PRAGMA rejected."
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "sql": {"type": "string"},
                        "limit": {"type": "integer", "default": 200},
                    },
                    "required": ["sql"],
                },
            },
            submit_diagnosis_tool(),
        ]

    def system_prompt(self) -> str:
        return load_system_prompt(self.code)

    def initial_user_message(self, *, mission_meta: dict[str, Any]) -> str:
        return (
            f"Mission {mission_meta.get('mission_id')} finished. "
            f"Composition={mission_meta.get('composition')}, "
            f"vendors={mission_meta.get('vendors')}. Diagnose any fault."
        )

    def execute_tool(self, call: ToolCall, *, mission_dir: str) -> ToolResult:
        db_path = os.path.join(mission_dir, "telemetry.sqlite")
        if call.name in {"list_tables", "describe_table", "query_sql"} and not os.path.exists(
            db_path
        ):
            return ToolResult(
                name=call.name,
                content=json.dumps({"error": "telemetry.sqlite not found"}),
                is_error=True,
            )
        if call.name == "list_tables":
            with sqlite3.connect(db_path) as conn:
                rows = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                ).fetchall()
            return ToolResult(name=call.name, content=json.dumps([r[0] for r in rows]))
        if call.name == "describe_table":
            table = str(call.arguments.get("table", ""))
            if not _safe_identifier(table):
                return ToolResult(
                    name=call.name,
                    content=json.dumps({"error": "invalid table name"}),
                    is_error=True,
                )
            with sqlite3.connect(db_path) as conn:
                rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
            return ToolResult(
                name=call.name,
                content=json.dumps([{"name": r[1], "type": r[2]} for r in rows]),
            )
        if call.name == "query_sql":
            sql = str(call.arguments.get("sql", "")).strip()
            limit = int(call.arguments.get("limit", 200))
            if not _is_read_only_select(sql):
                return ToolResult(
                    name=call.name,
                    content=json.dumps({"error": "only SELECT statements are allowed"}),
                    is_error=True,
                )
            # Defence in depth: strip a trailing ';' (so the subquery wrap is
            # valid) and cap the row count.
            inner = sql.rstrip().rstrip(";").rstrip()
            wrapped = f"SELECT * FROM ({inner}) LIMIT {limit}"
            try:
                with sqlite3.connect(db_path) as conn:
                    conn.execute("PRAGMA query_only = ON")
                    cur = conn.execute(wrapped)
                    cols = [d[0] for d in cur.description]
                    rows = cur.fetchall()
            except sqlite3.Error as exc:
                # Return the error to the agent so it can fix its query, rather
                # than crashing the whole run.
                return ToolResult(
                    name=call.name,
                    content=json.dumps({"error": f"SQL error: {exc}"}),
                    is_error=True,
                )
            return ToolResult(
                name=call.name,
                content=_bounded_result_json(cols, rows),
            )
        if call.name == "submit_diagnosis":
            return ToolResult(name=call.name, content=json.dumps({"received": True}))
        return ToolResult(
            name=call.name,
            content=json.dumps({"error": f"unknown tool {call.name!r}"}),
            is_error=True,
        )


def _safe_identifier(name: str) -> bool:
    return bool(name) and all(c.isalnum() or c == "_" for c in name)


def _is_read_only_select(sql: str) -> bool:
    """Reject obvious write/admin statements.

    Defence-in-depth — the connection is also opened with ``PRAGMA query_only``.
    """
    if not sql:
        return False
    lower = sql.lstrip().lower()
    if not lower.startswith(("select", "with")):
        return False
    blacklist = (
        " insert ",
        " update ",
        " delete ",
        " drop ",
        " alter ",
        " create ",
        " attach ",
        " detach ",
        " replace ",
        " pragma ",
    )
    padded = f" {lower} "
    return not any(b in padded for b in blacklist)


def _bounded_result_json(cols: list[str], rows: list[Any]) -> str:
    """Serialize a query result, dropping trailing rows if it is too large.

    Keeps the JSON under :data:`_MAX_RESULT_CHARS` so a single wide/array-valued
    result cannot overflow the model's context. Reports how many rows were kept
    vs returned so the agent knows to narrow its query.
    """
    full = json.dumps({"columns": cols, "rows": rows})
    if len(full) <= _MAX_RESULT_CHARS:
        return full
    kept = list(rows)
    while kept and len(json.dumps({"columns": cols, "rows": kept})) > _MAX_RESULT_CHARS:
        # Drop ~10% of the remaining rows per step for quick convergence.
        kept = kept[: max(1, int(len(kept) * 0.9) - 1)]
    return json.dumps(
        {
            "columns": cols,
            "rows": kept,
            "truncated": True,
            "rows_returned": len(kept),
            "rows_total": len(rows),
            "note": (
                "Result truncated to fit the context budget. Narrow the query: "
                "project only needed columns, add a WHERE filter, or aggregate."
            ),
        }
    )


register_condition(SqlCondition())
