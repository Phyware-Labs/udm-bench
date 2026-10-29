"""Tests for scoring.stats — detection breakdown + bootstrap CIs."""

from __future__ import annotations

from scoring.stats import (
    balanced_accuracy_ci,
    bootstrap_ci,
    cell_stats,
    detection_breakdown,
    rate_ci,
)


def test_detection_breakdown_counts():
    faulty = [True, True, False, None]  # 2 found, 2 missed (False + None)
    clean = [True, True, True, False]  # 3 correct-abstain, 1 false-alarm
    bd = detection_breakdown(faulty, clean)
    assert bd.found == 2
    assert bd.missed == 2
    assert bd.correct_abstain == 3
    assert bd.false_alarm == 1
    assert bd.n_faulty == 4
    assert bd.n_clean == 4
    assert bd.recall == 0.5
    assert bd.specificity == 0.75
    assert bd.balanced_accuracy == 0.625


def test_breakdown_empty_strata_return_none_rates():
    bd = detection_breakdown([], [])
    assert bd.recall is None
    assert bd.specificity is None
    assert bd.balanced_accuracy is None


def test_none_faulty_flag_counts_as_miss():
    bd = detection_breakdown([None, None], [])
    assert bd.found == 0
    assert bd.missed == 2


def test_bootstrap_ci_empty_is_none():
    assert bootstrap_ci([]) is None


def test_bootstrap_ci_single_value_collapses_to_point():
    ci = bootstrap_ci([1.0])
    assert ci is not None
    assert ci.point == 1.0
    assert ci.lo == 1.0
    assert ci.hi == 1.0
    assert ci.n == 1


def test_bootstrap_ci_all_same_has_zero_width():
    ci = bootstrap_ci([1.0, 1.0, 1.0, 1.0])
    assert ci is not None
    assert ci.point == 1.0
    assert ci.lo == 1.0
    assert ci.hi == 1.0


def test_bootstrap_ci_brackets_point_and_is_deterministic():
    values = [1.0, 0.0, 1.0, 0.0, 1.0, 0.0, 1.0, 0.0]
    ci1 = bootstrap_ci(values, seed=7)
    ci2 = bootstrap_ci(values, seed=7)
    assert ci1 is not None and ci2 is not None
    # Deterministic under a fixed seed.
    assert ci1.lo == ci2.lo
    assert ci1.hi == ci2.hi
    # Interval brackets the point estimate and stays within [0, 1].
    assert ci1.lo <= ci1.point <= ci1.hi
    assert 0.0 <= ci1.lo <= ci1.hi <= 1.0
    # A genuine mix produces a non-degenerate interval.
    assert ci1.hi > ci1.lo


def test_rate_ci_treats_none_as_failure_by_default():
    # 2 True out of 4 (Nones are failures) -> point 0.5.
    ci = rate_ci([True, True, None, None])
    assert ci is not None
    assert abs(ci.point - 0.5) < 1e-9


def test_rate_ci_empty_is_none():
    assert rate_ci([]) is None


def test_balanced_accuracy_ci_point_matches_manual():
    faulty = [True, True, False, False]  # recall 0.5
    clean = [True, True, True, False]  # specificity 0.75
    ci = balanced_accuracy_ci(faulty, clean, seed=1)
    assert ci is not None
    assert abs(ci.point - 0.625) < 1e-9
    assert ci.lo <= ci.point <= ci.hi


def test_balanced_accuracy_ci_needs_both_strata():
    assert balanced_accuracy_ci([True], [], seed=1) is None
    assert balanced_accuracy_ci([], [True], seed=1) is None


def test_cell_stats_to_dict_shape():
    stats = cell_stats([True, False], [True, True])
    d = stats.to_dict()
    assert set(d["detection_breakdown"].keys()) == {
        "found",
        "missed",
        "false_alarm",
        "correct_abstain",
        "n_faulty",
        "n_clean",
    }
    for key in ("recall_ci", "specificity_ci", "balanced_accuracy_ci"):
        assert key in d
        assert set(d[key].keys()) == {"point", "lo", "hi", "n"}
