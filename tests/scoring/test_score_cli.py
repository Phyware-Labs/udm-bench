"""End-to-end test of the scoring CLI + leaderboard renderer."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from leaderboard.render import render_html
from scoring import score


def _write_run(
    results: Path,
    *,
    run_id: str,
    mission_id: str,
    condition: str,
    model: str,
    composition: str,
    fault_id: str,
    claimed_time: float,
    vendor: str,
) -> None:
    rec = {
        "run_id": run_id,
        "mission_id": mission_id,
        "condition_code": condition,
        "model_id": model,
        "composition": composition,
        "vendors": ["tb3"] if composition == "single-vendor" else ["tb3", "px4"],
        "tool_calls": [],
        "final_diagnosis": {
            "fault_id": fault_id,
            "vendor": vendor,
            "source_id": vendor.replace("turtlebot3", "tb3") + "_0",
            "claimed_onset_time_s": claimed_time,
        },
        "final_content": "ok",
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "usd_cost": 0.01},
    }
    results.parent.mkdir(parents=True, exist_ok=True)
    with results.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, sort_keys=True))
        f.write("\n")


def _write_ground_truth(
    runs: Path, mission_id: str, *, vendor: str, fault_id: str, time: float
) -> None:
    mission_dir = runs / mission_id
    mission_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "mission_id": mission_id,
        "schema_version": 1,
        "injections": [
            {
                "vendor": vendor,
                "fault_id": fault_id,
                "source_id": vendor.replace("turtlebot3", "tb3") + "_0",
                "injection_time": time,
                "mission_id": mission_id,
                "parameters": {},
            }
        ],
    }
    (mission_dir / "ground_truth.json").write_text(json.dumps(payload), encoding="utf-8")


def test_score_main_writes_artifacts(tmp_path, capsys):
    runs = tmp_path / "runs"
    results = tmp_path / "results"

    # Single-vendor: 2 missions, both correct
    for i, mid in enumerate(["s1", "s2"]):
        _write_ground_truth(
            runs, mid, vendor="turtlebot3", fault_id="tb3_lidar_dropout", time=1.0 + i
        )
        _write_run(
            results / "single.jsonl",
            run_id=f"sr{i}",
            mission_id=mid,
            condition="C",
            model="claude-opus-4-7",
            composition="single-vendor",
            fault_id="tb3_lidar_dropout",
            claimed_time=1.0 + i,
            vendor="turtlebot3",
        )

    # Multi-vendor: 2 missions, 1 correct, 1 wrong
    _write_ground_truth(runs, "m1", vendor="px4", fault_id="px4_gps_dropout", time=10.0)
    _write_ground_truth(runs, "m2", vendor="px4", fault_id="px4_gps_dropout", time=11.0)
    _write_run(
        results / "multi.jsonl",
        run_id="mr1",
        mission_id="m1",
        condition="C",
        model="claude-opus-4-7",
        composition="multi-vendor",
        fault_id="px4_gps_dropout",
        claimed_time=10.0,
        vendor="px4",
    )
    _write_run(
        results / "multi.jsonl",
        run_id="mr2",
        mission_id="m2",
        condition="C",
        model="claude-opus-4-7",
        composition="multi-vendor",
        fault_id="tb3_motor_stall",  # WRONG fault id
        claimed_time=11.0,
        vendor="turtlebot3",  # WRONG vendor (truth is px4)
    )

    out = tmp_path / "out"
    rc = score.main(
        ["--runs", str(runs), "--results", str(results), "--out", str(out), "--log-level", "ERROR"]
    )
    assert rc == 0

    # Scorecards
    cards = (out / "scorecards.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(cards) == 4

    # Leaderboard
    lb = json.loads((out / "leaderboard.json").read_text(encoding="utf-8"))
    cells_by_comp = {c["composition"]: c for c in lb["cells"]}
    assert cells_by_comp["single-vendor"]["root_cause_accuracy"] == 1.0
    assert cells_by_comp["multi-vendor"]["root_cause_accuracy"] == 0.5

    # Efficiency + calibration metrics are first-class (back-fillable from records).
    for cell in lb["cells"]:
        assert "overall_accuracy" in cell
        assert "clean_mission_accuracy" in cell
        assert "latency_s_mean" in cell
        assert "prompt_tokens_mean" in cell
        # prompt_tokens were recorded (10 per run) -> mean surfaces them.
        assert cell["prompt_tokens_mean"] == 10.0

    # Delta CSV
    with (out / "composition_delta.csv").open("r", encoding="utf-8") as f:
        rows = {(r["condition_code"], r["metric"]): r for r in csv.DictReader(f)}
    delta = rows[("C", "root_cause_accuracy")]
    assert float(delta["single_vendor_value"]) == 1.0
    assert float(delta["multi_vendor_value"]) == 0.5
    assert float(delta["delta"]) == -0.5


def test_render_html_includes_matrix_and_delta(tmp_path):
    lb = {
        "cells": [
            {
                "condition_code": "C",
                "model_id": "claude-opus-4-7",
                "composition": "single-vendor",
                "n": 5,
                "n_faulty": 5,
                "root_cause_accuracy": 0.8,
                "cross_vendor_attribution_accuracy": None,
                "time_of_onset_error_s_mean": 1.0,
                "hallucination_total_mean": 0.0,
                "tool_call_count_mean": 4.0,
                "usd_cost_mean": 0.10,
                "usd_cost_total": 0.50,
            },
            {
                "condition_code": "C",
                "model_id": "claude-opus-4-7",
                "composition": "multi-vendor",
                "n": 5,
                "n_faulty": 5,
                "root_cause_accuracy": 0.6,
                "cross_vendor_attribution_accuracy": 0.5,
                "time_of_onset_error_s_mean": 2.0,
                "hallucination_total_mean": 1.0,
                "tool_call_count_mean": 6.0,
                "usd_cost_mean": 0.12,
                "usd_cost_total": 0.60,
            },
        ],
        "n_runs_total": 10,
    }
    deltas = [
        {
            "condition_code": "C",
            "model_id": "claude-opus-4-7",
            "metric": "root_cause_accuracy",
            "single_vendor_value": "0.8",
            "multi_vendor_value": "0.6",
            "delta": "-0.2",
            "single_vendor_n": "5",
            "multi_vendor_n": "5",
        }
    ]
    html_str = render_html(leaderboard=lb, deltas=deltas)
    assert "udm-bench leaderboard" in html_str
    assert "claude-opus-4-7" in html_str
    assert "80.00%" in html_str
    assert "delta" in html_str.lower()


def test_render_html_no_deltas_falls_back():
    html_str = render_html(leaderboard={"cells": [], "n_runs_total": 0}, deltas=[])
    assert "No delta rows yet" in html_str


def test_leaderboard_cli(tmp_path):
    from leaderboard import render

    lb_path = tmp_path / "leaderboard.json"
    delta_path = tmp_path / "composition_delta.csv"
    out_dir = tmp_path / "out"

    lb_path.write_text(json.dumps({"cells": [], "n_runs_total": 0}), encoding="utf-8")
    delta_path.write_text(
        "condition_code,model_id,metric,single_vendor_value,multi_vendor_value,delta,single_vendor_n,multi_vendor_n\n",
        encoding="utf-8",
    )
    rc = render.main(
        [
            "--leaderboard",
            str(lb_path),
            "--delta",
            str(delta_path),
            "--out",
            str(out_dir),
        ]
    )
    assert rc == 0
    assert (out_dir / "index.html").exists()


def test_score_main_returns_1_when_empty(tmp_path, capsys):
    runs = tmp_path / "runs"
    runs.mkdir()
    results = tmp_path / "results"
    results.mkdir()
    rc = score.main(
        [
            "--runs",
            str(runs),
            "--results",
            str(results),
            "--out",
            str(tmp_path / "out"),
            "--log-level",
            "ERROR",
        ]
    )
    assert rc == 1
