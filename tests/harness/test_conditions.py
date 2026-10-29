"""Condition plugin tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from harness.backends.base import ToolCall
from harness.conditions import (
    a_raw_bag,
    b_sql,
    get_condition,
    registered_conditions,
)


def test_all_conditions_registered():
    assert set(registered_conditions()) == {"A", "B", "C", "D", "E", "F", "G"}


@pytest.mark.parametrize("code", ["A", "B"])
def test_conditions_have_tool_specs_and_prompts(code):
    cond = get_condition(code)
    specs = cond.tool_specs()
    assert specs
    for s in specs:
        assert s["name"]
        assert "input_schema" in s
    assert cond.system_prompt()
    assert cond.initial_user_message(mission_meta={"mission_id": "m1"})


@pytest.mark.parametrize("code", ["A", "B"])
def test_submit_diagnosis_exposes_fault_taxonomy(code):
    from harness.conditions._diagnosis import NO_FAULT_FAULT_ID, fault_id_enum

    cond = get_condition(code)
    spec = next(t for t in cond.tool_specs() if t["name"] == "submit_diagnosis")
    fault_id = spec["input_schema"]["properties"]["fault_id"]
    # Every condition shares the same canonical answer label space.
    assert set(fault_id["enum"]) == set(fault_id_enum())
    assert "tb3_imu_bias" in fault_id["enum"]
    assert "px4_gps_dropout" in fault_id["enum"]
    assert NO_FAULT_FAULT_ID in fault_id["enum"]
    # vendor is constrained too (cross-vendor attribution scoring).
    assert spec["input_schema"]["properties"]["vendor"]["enum"] == ["turtlebot3", "px4"]


# ----------------------------- Condition A ---------------------------------


def test_raw_bag_reads_existing_file(tmp_path):
    cond = a_raw_bag.RawBagCondition()
    (tmp_path / "bag_turtlebot3_tb3_0.txt").write_text("line1\nline2\n", encoding="utf-8")
    res = cond.execute_tool(
        ToolCall(name="read_bag_text", arguments={"vendor": "turtlebot3", "source_id": "tb3_0"}),
        mission_dir=str(tmp_path),
    )
    assert "line1" in res.content
    assert not res.is_error


def test_raw_bag_handles_missing_file(tmp_path):
    cond = a_raw_bag.RawBagCondition()
    res = cond.execute_tool(
        ToolCall(name="read_bag_text", arguments={"vendor": "px4", "source_id": "px4_0"}),
        mission_dir=str(tmp_path),
    )
    assert res.is_error


def test_raw_bag_unknown_tool_is_error(tmp_path):
    cond = a_raw_bag.RawBagCondition()
    res = cond.execute_tool(ToolCall(name="zonk", arguments={}), mission_dir=str(tmp_path))
    assert res.is_error


def test_raw_bag_diagnosis_acked(tmp_path):
    cond = a_raw_bag.RawBagCondition()
    res = cond.execute_tool(
        ToolCall(name="submit_diagnosis", arguments={"fault_id": "x"}), mission_dir=str(tmp_path)
    )
    assert not res.is_error


def test_raw_bag_list_sources(tmp_path):
    cond = a_raw_bag.RawBagCondition()
    (tmp_path / "bag_turtlebot3_tb3_0.txt").write_text("x", encoding="utf-8")
    (tmp_path / "bag_px4_px4_0.txt").write_text("x", encoding="utf-8")
    (tmp_path / "telemetry.sqlite").write_text("x", encoding="utf-8")  # ignored
    res = cond.execute_tool(ToolCall(name="list_sources", arguments={}), mission_dir=str(tmp_path))
    assert not res.is_error
    sources = json.loads(res.content)
    assert {"vendor": "turtlebot3", "source_id": "tb3_0"} in sources
    assert {"vendor": "px4", "source_id": "px4_0"} in sources
    assert len(sources) == 2


def test_raw_bag_missing_file_lists_available(tmp_path):
    cond = a_raw_bag.RawBagCondition()
    (tmp_path / "bag_turtlebot3_tb3_0.txt").write_text("x", encoding="utf-8")
    res = cond.execute_tool(
        ToolCall(name="read_bag_text", arguments={"vendor": "px4", "source_id": "wrong"}),
        mission_dir=str(tmp_path),
    )
    assert res.is_error
    payload = json.loads(res.content)
    # The error hints at what *is* available so the agent can recover.
    assert payload["available"] == [{"vendor": "turtlebot3", "source_id": "tb3_0"}]


def test_raw_bag_paginates_with_header(tmp_path):
    cond = a_raw_bag.RawBagCondition()
    body = "".join(f"line{i}\n" for i in range(50))
    (tmp_path / "bag_turtlebot3_tb3_0.txt").write_text(body, encoding="utf-8")
    res = cond.execute_tool(
        ToolCall(
            name="read_bag_text",
            arguments={
                "vendor": "turtlebot3",
                "source_id": "tb3_0",
                "start_line": 10,
                "max_lines": 5,
            },
        ),
        mission_dir=str(tmp_path),
    )
    assert not res.is_error
    header_line, _, text = res.content.partition("\n")
    header = json.loads(header_line)
    assert header["total_lines"] == 50
    assert header["start_line"] == 10
    assert header["returned_lines"] == 5
    assert header["next_start_line"] == 15
    assert "line10" in text and "line14" in text
    assert "line15" not in text


def test_raw_bag_caps_max_lines(tmp_path):
    cond = a_raw_bag.RawBagCondition()
    body = "".join(f"x{i}\n" for i in range(5000))
    (tmp_path / "bag_turtlebot3_tb3_0.txt").write_text(body, encoding="utf-8")
    res = cond.execute_tool(
        ToolCall(
            name="read_bag_text",
            arguments={"vendor": "turtlebot3", "source_id": "tb3_0", "max_lines": 999999},
        ),
        mission_dir=str(tmp_path),
    )
    header = json.loads(res.content.split("\n", 1)[0])
    assert header["returned_lines"] <= 1000  # hard cap enforced


# ----------------------------- Condition B ---------------------------------


def _build_db(tmp_path: Path) -> Path:
    import sqlite3

    p = tmp_path / "telemetry.sqlite"
    with sqlite3.connect(p) as conn:
        conn.execute("CREATE TABLE tb3_scan (t REAL, ranges TEXT)")
        conn.executemany("INSERT INTO tb3_scan VALUES (?, ?)", [(1.0, "a"), (2.0, "b"), (3.0, "c")])
        conn.execute("CREATE TABLE px4_battery (t REAL, voltage REAL)")
        conn.executemany("INSERT INTO px4_battery VALUES (?, ?)", [(1.0, 16.0), (2.0, 13.8)])
    return p


def test_sql_list_describe_query(tmp_path):
    _build_db(tmp_path)
    cond = b_sql.SqlCondition()
    res = cond.execute_tool(ToolCall(name="list_tables", arguments={}), mission_dir=str(tmp_path))
    assert "tb3_scan" in res.content

    res = cond.execute_tool(
        ToolCall(name="describe_table", arguments={"table": "tb3_scan"}),
        mission_dir=str(tmp_path),
    )
    payload = json.loads(res.content)
    cols = {c["name"] for c in payload}
    assert {"t", "ranges"} <= cols

    res = cond.execute_tool(
        ToolCall(name="query_sql", arguments={"sql": "SELECT * FROM tb3_scan"}),
        mission_dir=str(tmp_path),
    )
    payload = json.loads(res.content)
    assert payload["columns"] == ["t", "ranges"]
    assert len(payload["rows"]) == 3


def test_sql_large_result_is_truncated(tmp_path):
    import sqlite3

    p = tmp_path / "telemetry.sqlite"
    big = "x" * 2000  # wide cell so a few hundred rows overflow the cap
    with sqlite3.connect(p) as conn:
        conn.execute("CREATE TABLE tb3_wide (t REAL, blob TEXT)")
        conn.executemany(
            "INSERT INTO tb3_wide VALUES (?, ?)", [(float(i), big) for i in range(500)]
        )
    cond = b_sql.SqlCondition()
    res = cond.execute_tool(
        ToolCall(name="query_sql", arguments={"sql": "SELECT * FROM tb3_wide", "limit": 500}),
        mission_dir=str(tmp_path),
    )
    payload = json.loads(res.content)
    assert payload.get("truncated") is True
    assert payload["rows_returned"] < payload["rows_total"]
    assert len(res.content) <= b_sql._MAX_RESULT_CHARS


def test_sql_rejects_write_statements(tmp_path):
    _build_db(tmp_path)
    cond = b_sql.SqlCondition()
    for sql in [
        "DELETE FROM tb3_scan",
        "INSERT INTO tb3_scan VALUES (4, 'd')",
        "DROP TABLE tb3_scan",
        "PRAGMA writable_schema = 1",
        "",
    ]:
        res = cond.execute_tool(
            ToolCall(name="query_sql", arguments={"sql": sql}), mission_dir=str(tmp_path)
        )
        assert res.is_error, f"expected rejection for {sql!r}"


def test_sql_describe_rejects_unsafe_identifier(tmp_path):
    _build_db(tmp_path)
    cond = b_sql.SqlCondition()
    res = cond.execute_tool(
        ToolCall(name="describe_table", arguments={"table": "tb3_scan; DROP TABLE x"}),
        mission_dir=str(tmp_path),
    )
    assert res.is_error


def test_sql_missing_db_returns_error(tmp_path):
    cond = b_sql.SqlCondition()
    res = cond.execute_tool(ToolCall(name="list_tables", arguments={}), mission_dir=str(tmp_path))
    assert res.is_error


def test_sql_unknown_tool_returns_error(tmp_path):
    _build_db(tmp_path)
    cond = b_sql.SqlCondition()
    res = cond.execute_tool(ToolCall(name="bogus", arguments={}), mission_dir=str(tmp_path))
    assert res.is_error


def test_sql_diagnosis_acked(tmp_path):
    cond = b_sql.SqlCondition()
    res = cond.execute_tool(
        ToolCall(name="submit_diagnosis", arguments={}), mission_dir=str(tmp_path)
    )
    assert not res.is_error


def test_sql_strips_trailing_semicolon(tmp_path):
    _build_db(tmp_path)
    cond = b_sql.SqlCondition()
    res = cond.execute_tool(
        ToolCall(name="query_sql", arguments={"sql": "SELECT * FROM tb3_scan;"}),
        mission_dir=str(tmp_path),
    )
    assert not res.is_error
    assert json.loads(res.content)["columns"] == ["t", "ranges"]


def test_sql_bad_query_returns_error_not_crash(tmp_path):
    _build_db(tmp_path)
    cond = b_sql.SqlCondition()
    res = cond.execute_tool(
        ToolCall(name="query_sql", arguments={"sql": "SELECT * FROM no_such_table"}),
        mission_dir=str(tmp_path),
    )
    assert res.is_error
    assert "SQL error" in json.loads(res.content)["error"]


def test_baseline_conditions_have_no_orientation_preamble():
    # A/B do not enumerate a UDM store, so no preamble is injected.
    assert (
        a_raw_bag.RawBagCondition().orientation_preamble(mission_dir=".", mission_meta={}) is None
    )
    assert b_sql.SqlCondition().orientation_preamble(mission_dir=".", mission_meta={}) is None


# ----------------------------- Registry edge cases -------------------------


def test_registry_unknown_code_raises():
    with pytest.raises(KeyError):
        get_condition("Z")


def test_condition_base_requires_code_and_name():
    from harness.conditions.base import Condition

    class Bad(Condition):
        def tool_specs(self):
            return []

        def system_prompt(self):
            return ""

        def initial_user_message(self, *, mission_meta):
            return ""

        def execute_tool(self, call, *, mission_dir):
            from harness.conditions.base import ToolResult

            return ToolResult(name=call.name, content="")

    with pytest.raises(TypeError, match="code"):
        Bad()
