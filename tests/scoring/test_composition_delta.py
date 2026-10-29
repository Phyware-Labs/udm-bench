"""Tests for the same-vs-multi-vendor delta calculator."""

from __future__ import annotations

from scoring.composition_delta import compute_composition_deltas
from scoring.hallucination import HallucinationReport
from scoring.metrics import Scorecard


def _card(**overrides) -> Scorecard:
    base = {
        "run_id": "r1",
        "mission_id": "m1",
        "condition_code": "C",
        "model_id": "claude-opus-4-7",
        "composition": "single-vendor",
        "is_clean_mission": False,
        "root_cause_correct": True,
        "cross_vendor_attribution_correct": None,
        "time_of_onset_error_s": 1.0,
        "hallucination": HallucinationReport(),
        "tool_call_count": 4,
        "usd_cost": 0.10,
        "submitted_diagnosis": True,
    }
    base.update(overrides)
    return Scorecard(**base)


def test_deltas_skip_clean_missions():
    cards = [
        _card(is_clean_mission=True),
        _card(is_clean_mission=True, composition="multi-vendor"),
    ]
    out = compute_composition_deltas(cards)
    assert out == []


def test_deltas_require_both_compositions():
    cards = [_card(composition="single-vendor"), _card(composition="single-vendor")]
    out = compute_composition_deltas(cards)
    assert out == []


def test_deltas_compute_for_paired_cells():
    cards = [
        _card(composition="single-vendor", root_cause_correct=True, time_of_onset_error_s=1.0),
        _card(composition="single-vendor", root_cause_correct=True, time_of_onset_error_s=2.0),
        _card(composition="multi-vendor", root_cause_correct=False, time_of_onset_error_s=3.0),
        _card(composition="multi-vendor", root_cause_correct=True, time_of_onset_error_s=4.0),
    ]
    deltas = {
        (d.metric, d.condition_code, d.model_id): d for d in compute_composition_deltas(cards)
    }
    rca = deltas[("root_cause_accuracy", "C", "claude-opus-4-7")]
    assert rca.single_vendor_value == 1.0
    assert rca.multi_vendor_value == 0.5
    assert rca.delta == -0.5
    onset = deltas[("time_of_onset_error_s", "C", "claude-opus-4-7")]
    assert onset.single_vendor_value == 1.5
    assert onset.multi_vendor_value == 3.5
    assert onset.delta == 2.0


def test_deltas_handle_separate_models_independently():
    cards = [
        _card(model_id="m1", composition="single-vendor", root_cause_correct=True),
        _card(model_id="m1", composition="multi-vendor", root_cause_correct=False),
        _card(model_id="m2", composition="single-vendor", root_cause_correct=False),
        _card(model_id="m2", composition="multi-vendor", root_cause_correct=True),
    ]
    deltas = compute_composition_deltas(cards)
    by_model = {d.model_id: d for d in deltas if d.metric == "root_cause_accuracy"}
    assert by_model["m1"].delta == -1.0
    assert by_model["m2"].delta == 1.0
