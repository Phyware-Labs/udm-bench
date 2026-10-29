"""Tests for scoring.metrics."""

from __future__ import annotations

from faults.base import InjectionRecord
from scoring.metrics import NO_FAULT_FAULT_ID, score_run


def _gt(**overrides) -> InjectionRecord:
    defaults = {
        "vendor": "turtlebot3",
        "fault_id": "tb3_lidar_dropout",
        "source_id": "tb3_0",
        "injection_time": 12.5,
        "mission_id": "m1",
        "parameters": {},
    }
    defaults.update(overrides)
    return InjectionRecord(**defaults)


def _run(**overrides):
    base = {
        "run_id": "r1",
        "mission_id": "m1",
        "condition_code": "C",
        "model_id": "claude-opus-4-7",
        "composition": "single-vendor",
        "vendors": ["tb3"],
        "tool_calls": [],
        "final_diagnosis": None,
        "final_content": "",
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "usd_cost": 0.05},
    }
    base.update(overrides)
    return base


def test_correct_diagnosis_scores_true():
    rec = _run(
        final_diagnosis={
            "fault_id": "tb3_lidar_dropout",
            "vendor": "turtlebot3",
            "source_id": "tb3_0",
            "claimed_onset_time_s": 13.0,
        }
    )
    card = score_run(rec, ground_truth=[_gt()])
    assert card.root_cause_correct is True
    assert card.time_of_onset_error_s == 0.5
    assert card.cross_vendor_attribution_correct is None  # single-vendor


def test_implausible_onset_epoch_is_dropped():
    # A model that emits an absolute Unix epoch instead of a mission-relative
    # offset must not corrupt the onset metric — it is scored as None.
    rec = _run(
        final_diagnosis={
            "fault_id": "tb3_lidar_dropout",
            "vendor": "turtlebot3",
            "source_id": "tb3_0",
            "claimed_onset_time_s": 1782776199.0,
        }
    )
    card = score_run(rec, ground_truth=[_gt()])
    assert card.root_cause_correct is True  # diagnosis still counts
    assert card.time_of_onset_error_s is None  # implausible onset dropped


def test_incorrect_diagnosis_scores_false():
    rec = _run(
        final_diagnosis={
            "fault_id": "tb3_motor_stall",
            "vendor": "turtlebot3",
            "source_id": "tb3_0",
            "claimed_onset_time_s": 1.0,
        }
    )
    card = score_run(rec, ground_truth=[_gt()])
    assert card.root_cause_correct is False


def test_missing_diagnosis_in_faulty_mission_scores_false():
    rec = _run(final_diagnosis=None)
    card = score_run(rec, ground_truth=[_gt()])
    assert card.root_cause_correct is False
    assert card.cross_vendor_attribution_correct is None  # single-vendor


def test_clean_mission_no_diagnosis_scores_correct():
    rec = _run(final_diagnosis=None)
    card = score_run(rec, ground_truth=[])
    assert card.is_clean_mission
    assert card.root_cause_correct is True
    assert card.time_of_onset_error_s is None


def test_clean_mission_no_fault_diagnosis_scores_correct():
    rec = _run(
        final_diagnosis={
            "fault_id": NO_FAULT_FAULT_ID,
            "vendor": "turtlebot3",
            "source_id": "tb3_0",
            "claimed_onset_time_s": 0.0,
        }
    )
    card = score_run(rec, ground_truth=[])
    assert card.root_cause_correct is True


def test_clean_mission_with_false_alarm_scores_false():
    rec = _run(
        final_diagnosis={
            "fault_id": "tb3_lidar_dropout",
            "vendor": "turtlebot3",
            "source_id": "tb3_0",
            "claimed_onset_time_s": 5.0,
        }
    )
    card = score_run(rec, ground_truth=[])
    assert card.root_cause_correct is False


def test_multi_vendor_cross_vendor_attribution():
    rec = _run(
        composition="multi-vendor",
        vendors=["tb3", "px4"],
        final_diagnosis={
            "fault_id": "px4_gps_dropout",
            "vendor": "px4",
            "source_id": "px4_0",
            "claimed_onset_time_s": 20.0,
        },
    )
    gt = _gt(vendor="px4", fault_id="px4_gps_dropout", source_id="px4_0", injection_time=18.0)
    card = score_run(rec, ground_truth=[gt])
    assert card.cross_vendor_attribution_correct is True
    assert card.root_cause_correct is True


def test_multi_vendor_wrong_vendor_attribution():
    rec = _run(
        composition="multi-vendor",
        vendors=["tb3", "px4"],
        final_diagnosis={
            "fault_id": "tb3_lidar_dropout",
            "vendor": "turtlebot3",
            "source_id": "tb3_0",
            "claimed_onset_time_s": 20.0,
        },
    )
    gt = _gt(vendor="px4", fault_id="px4_gps_dropout", source_id="px4_0", injection_time=18.0)
    card = score_run(rec, ground_truth=[gt])
    assert card.cross_vendor_attribution_correct is False


def test_score_run_loads_ground_truth_from_disk(tmp_path):
    import json

    runs = tmp_path / "runs" / "m1"
    runs.mkdir(parents=True)
    (runs / "ground_truth.json").write_text(
        json.dumps(
            {
                "mission_id": "m1",
                "schema_version": 1,
                "injections": [
                    {
                        "vendor": "turtlebot3",
                        "fault_id": "tb3_lidar_dropout",
                        "source_id": "tb3_0",
                        "injection_time": 5.0,
                        "mission_id": "m1",
                        "parameters": {},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    rec = _run(
        final_diagnosis={
            "fault_id": "tb3_lidar_dropout",
            "vendor": "turtlebot3",
            "source_id": "tb3_0",
            "claimed_onset_time_s": 5.5,
        }
    )
    card = score_run(rec, runs_root=tmp_path / "runs")
    assert card.root_cause_correct is True
    assert card.time_of_onset_error_s == 0.5
