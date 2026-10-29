"""End-to-end Phase 2 pipeline pilot (no API spend).

Exercises the full baseline path on a synthetic mission:

    recorded bag -> baselines.prepare -> Condition A/B tool surface
                 -> harness.run_one (mock backend) -> RunRecord

This is the cheap, deterministic proof that the converters feed the harness
correctly; the paid live matrix simply swaps the ``mock`` backend for a real
model id.
"""

from __future__ import annotations

import json
from pathlib import Path

from baselines.prepare import prepare_mission
from harness import run as run_mod
from harness.backends import ModelOutput, ToolCall, register_backend
from harness.backends.mock import MockBackend
from tests.baselines._bagfixture import make_twist, write_bag

TWIST = "geometry_msgs/msg/Twist"


def _mission_with_bag(tmp_path: Path) -> Path:
    mission_dir = tmp_path / "runs" / "pilot-mission-0001"
    mission_dir.mkdir(parents=True)
    (mission_dir / "mission_meta.json").write_text(
        json.dumps(
            {
                "mission_id": "pilot-mission-0001",
                "composition": "single-vendor",
                "vendors": ["tb3"],
                "world": "small_warehouse",
                "seed": 1,
                "injections": [],
                "mission_template": {},
            }
        ),
        encoding="utf-8",
    )
    write_bag(
        mission_dir / "bag_turtlebot3_tb3_0",
        [
            ("/cmd_vel", TWIST, 1_000_000_000, make_twist(0.10, 0.0)),
            ("/cmd_vel", TWIST, 2_000_000_000, make_twist(0.20, 0.3)),
            ("/cmd_vel", TWIST, 3_000_000_000, make_twist(0.00, -0.3)),
        ],
    )
    return mission_dir


def _register(model_id: str, responses):
    register_backend(model_id, lambda **kw: MockBackend(responses=list(responses), **kw))


def test_condition_a_pilot_reads_prepared_text(tmp_path):
    mission_dir = _mission_with_bag(tmp_path)
    summary = prepare_mission(mission_dir)
    assert summary.text_files["bag_turtlebot3_tb3_0.txt"] == 3

    responses = [
        ModelOutput(
            content="inspecting",
            tool_calls=(
                ToolCall(
                    name="read_bag_text",
                    arguments={"vendor": "turtlebot3", "source_id": "tb3_0"},
                ),
            ),
        ),
        ModelOutput(
            content="done",
            tool_calls=(
                ToolCall(
                    name="submit_diagnosis",
                    arguments={
                        "fault_id": "none",
                        "vendor": "turtlebot3",
                        "source_id": "tb3_0",
                        "claimed_onset_time_s": 0.0,
                    },
                ),
            ),
        ),
    ]
    _register("mock-a", responses)
    record = run_mod.run_one(mission_dir=mission_dir, condition_code="A", model_id="mock-a")

    # The first tool result must contain real decoded telemetry from the bag.
    bag_read = record.tool_calls[0]
    assert not bag_read["tool_result"]["is_error"]
    assert "/cmd_vel" in bag_read["tool_result"]["content"]
    assert record.final_diagnosis is not None
    assert record.error is None


def test_condition_b_pilot_queries_prepared_sqlite(tmp_path):
    mission_dir = _mission_with_bag(tmp_path)
    prepare_mission(mission_dir)

    responses = [
        ModelOutput(
            content="listing",
            tool_calls=(ToolCall(name="list_tables", arguments={}),),
        ),
        ModelOutput(
            content="querying",
            tool_calls=(
                ToolCall(
                    name="query_sql",
                    arguments={"sql": "SELECT linear__x FROM turtlebot3__cmd_vel"},
                ),
            ),
        ),
        ModelOutput(
            content="done",
            tool_calls=(
                ToolCall(
                    name="submit_diagnosis",
                    arguments={
                        "fault_id": "none",
                        "vendor": "turtlebot3",
                        "source_id": "tb3_0",
                        "claimed_onset_time_s": 0.0,
                    },
                ),
            ),
        ),
    ]
    _register("mock-b", responses)
    record = run_mod.run_one(mission_dir=mission_dir, condition_code="B", model_id="mock-b")

    list_result = json.loads(record.tool_calls[0]["tool_result"]["content"])
    assert "turtlebot3__cmd_vel" in list_result

    query_result = json.loads(record.tool_calls[1]["tool_result"]["content"])
    assert query_result["columns"] == ["linear__x"]
    assert len(query_result["rows"]) == 3
    assert record.final_diagnosis is not None
    assert record.error is None
