"""End-to-end smoke pipeline on the public code path.

Runs the whole control flow on synthetic missions with the mock LLM backend
(no Docker, no ROS2, no API keys) and asserts that:

  mission dir (mission_meta + ground_truth + bag)
            -> baselines.prepare writes the Condition A text and B SQLite
            -> harness run (Conditions A and B) produces a RunRecord
            -> scoring CLI produces scorecards + leaderboard.json + composition_delta.csv
            -> leaderboard renderer produces index.html
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from baselines.prepare import prepare_mission
from faults import GroundTruthLogger, InjectionRecord
from harness import run as harness_run
from harness.backends import ModelOutput, ToolCall, register_backend
from harness.backends.mock import MockBackend
from leaderboard.render import render_html
from scoring import score
from tests.baselines._bagfixture import make_twist, write_bag

TWIST = "geometry_msgs/msg/Twist"

# (mission suffix, injected fault or None for a clean mission)
MISSIONS: list[tuple[str, str | None]] = [
    ("0001", "tb3_lidar_dropout"),
    ("0002", None),
    ("0003", "tb3_motor_stall"),
    ("0004", None),
]


def _make_mission(runs_root: Path, suffix: str, fault_id: str | None) -> Path:
    mission_id = f"single_tb3_warehouse_nav-smoke{suffix}"
    mission_dir = runs_root / mission_id
    mission_dir.mkdir(parents=True)
    injections = (
        [
            {
                "fault_id": fault_id,
                "vendor": "turtlebot3",
                "source_id": "tb3_0",
                "injection_time_s": 1.5,
            }
        ]
        if fault_id
        else []
    )
    (mission_dir / "mission_meta.json").write_text(
        json.dumps(
            {
                "mission_id": mission_id,
                "composition": "single-vendor",
                "vendors": ["tb3"],
                "world": "small_warehouse",
                "seed": 1,
                "injections": injections,
                "mission_template": {},
            }
        ),
        encoding="utf-8",
    )
    if fault_id:
        GroundTruthLogger(runs_root=runs_root, mission_id=mission_id).log(
            InjectionRecord(
                vendor="turtlebot3",
                fault_id=fault_id,
                source_id="tb3_0",
                injection_time=1.5,
                mission_id=mission_id,
            )
        )
    write_bag(
        mission_dir / "bag_turtlebot3_tb3_0",
        [
            ("/cmd_vel", TWIST, 1_000_000_000, make_twist(0.10, 0.0)),
            ("/cmd_vel", TWIST, 2_000_000_000, make_twist(0.20, 0.3)),
        ],
    )
    prepare_mission(mission_dir)
    return mission_dir


def _register_mock(model_id: str, *, fault_id: str):
    """Register a one-shot mock backend that submits a fixed diagnosis."""
    responses = [
        ModelOutput(
            content="diagnosis-submitted",
            tool_calls=(
                ToolCall(
                    name="submit_diagnosis",
                    arguments={
                        "fault_id": fault_id,
                        "vendor": "turtlebot3",
                        "source_id": "tb3_0",
                        "claimed_onset_time_s": 1.5,
                        "explanation": "end-to-end smoke fixture",
                    },
                ),
            ),
        ),
    ]
    register_backend(model_id, lambda **kw: MockBackend(responses=list(responses), **kw))


def _run_all(runs_root: Path, results_root: Path, *, condition: str, model_id: str, answer):
    for suffix, fault_id in MISSIONS:
        mission_dir = runs_root / f"single_tb3_warehouse_nav-smoke{suffix}"
        _register_mock(model_id, fault_id=answer(fault_id))
        record = harness_run.run_one(
            mission_dir=mission_dir, condition_code=condition, model_id=model_id
        )
        assert record.error is None
        assert record.final_diagnosis is not None
        harness_run.append_jsonl(results_root / f"{record.run_id}.jsonl", record)


def _score(runs_root: Path, results_root: Path, out: Path) -> dict:
    rc = score.main(
        [
            "--runs",
            str(runs_root),
            "--results",
            str(results_root),
            "--out",
            str(out),
            "--log-level",
            "ERROR",
        ]
    )
    assert rc == 0
    for name in ("leaderboard.json", "composition_delta.csv", "scorecards.jsonl"):
        assert (out / name).exists()
    return json.loads((out / "leaderboard.json").read_text(encoding="utf-8"))


@pytest.mark.smoke
def test_full_public_pipeline(tmp_path):
    runs_root = tmp_path / "runs"
    results_root = tmp_path / "results"
    scoring_out = tmp_path / "scoring_out"
    for suffix, fault_id in MISSIONS:
        _make_mission(runs_root, suffix, fault_id)

    # Correct answers from both baselines: the fault on faulty missions,
    # no_fault on clean ones.
    for condition in ("A", "B"):
        _run_all(
            runs_root,
            results_root,
            condition=condition,
            model_id="mock-smoke",
            answer=lambda f: f or "no_fault",
        )

    lb = _score(runs_root, results_root, scoring_out)
    assert lb["n_runs_total"] == 2 * len(MISSIONS)
    cells = [c for c in lb["cells"] if c["composition"] == "single-vendor"]
    assert {c["condition_code"] for c in cells} == {"A", "B"}
    for cell in cells:
        assert cell["root_cause_accuracy"] == 1.0

    deltas = list(csv.DictReader((scoring_out / "composition_delta.csv").open(encoding="utf-8")))
    rendered = render_html(leaderboard=lb, deltas=deltas)
    assert "udm-bench leaderboard" in rendered
    assert "single-vendor" in rendered


@pytest.mark.smoke
def test_pipeline_handles_diagnosis_mismatch(tmp_path):
    """A wrong-fault diagnosis must show up in the leaderboard as < 100% accuracy."""
    runs_root = tmp_path / "runs"
    results_root = tmp_path / "results"
    for suffix, fault_id in MISSIONS:
        _make_mission(runs_root, suffix, fault_id)

    _run_all(
        runs_root,
        results_root,
        condition="A",
        model_id="mock-wrong",
        answer=lambda f: "tb3_imu_bias" if f else "no_fault",
    )
    lb = _score(runs_root, results_root, tmp_path / "scoring_out")
    cells = [c for c in lb["cells"] if c["n_faulty"] > 0]
    assert cells, "no faulty cells produced"
    for cell in cells:
        assert cell["root_cause_accuracy"] == 0.0


def test_udm_conditions_explain_they_are_not_included(tmp_path):
    from harness.conditions import get_condition
    from harness.conditions.unavailable import ConditionNotIncluded

    for code in "CDEFG":
        cond = get_condition(code)
        with pytest.raises(ConditionNotIncluded, match="not included"):
            cond.tool_specs()
