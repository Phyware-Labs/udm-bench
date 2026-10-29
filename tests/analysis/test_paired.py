"""Tests for analysis.paired — McNemar, Cohen's h, paired bootstrap, Holm."""

from __future__ import annotations

import math

import pytest

from analysis.paired import (
    balanced_stat,
    cohens_h,
    composition_delta_stat,
    holm,
    mcnemar_exact,
    paired_bootstrap_diff,
    recall_stat,
    stratified_bootstrap,
)


def test_mcnemar_counts_only_discordant_pairs():
    x = [True, True, True, False, False, True]
    y = [True, False, False, False, True, True]
    r = mcnemar_exact(x, y)
    assert (r.b, r.c) == (2, 1)
    # n=3, k=1: 2 * (C(3,0) + C(3,1)) / 8 = 1.0
    assert r.p == pytest.approx(1.0)


def test_mcnemar_all_one_sided():
    # 8 discordant, all favouring x: p = 2 / 2**8
    r = mcnemar_exact([True] * 8 + [False] * 4, [False] * 8 + [False] * 4)
    assert r.p == pytest.approx(2 / 256)


def test_mcnemar_no_discordance_is_p_one():
    assert mcnemar_exact([True, False], [True, False]).p == 1.0


def test_mcnemar_rejects_unequal_lengths():
    with pytest.raises(ValueError):
        mcnemar_exact([True], [True, False])


def test_cohens_h_symmetry_and_known_value():
    assert cohens_h(0.5, 0.5) == 0.0
    assert cohens_h(0.2, 0.6) == pytest.approx(-cohens_h(0.6, 0.2))
    assert cohens_h(1.0, 0.0) == pytest.approx(math.pi)


def test_holm_matches_hand_computation():
    # sorted: 0.01*3=0.03, 0.02*2=0.04, 0.04*1=0.04 (monotone)
    assert holm([0.04, 0.01, 0.02]) == pytest.approx([0.04, 0.03, 0.04])
    assert holm([0.9, 0.8]) == pytest.approx([1.0, 1.0])


def test_stats_on_strata():
    vals = [1.0, 0.0, 1.0, 1.0]
    strata = ["faulty", "faulty", "clean", "clean"]
    assert recall_stat(vals, strata) == 0.5
    assert balanced_stat(vals, strata) == 0.75
    comp = ["single-vendor", "single-vendor", "multi-vendor", "multi-vendor"]
    assert composition_delta_stat(vals, comp) == 0.5


def test_paired_bootstrap_identical_conditions_is_zero():
    x = [1.0, 0.0, 1.0, 0.0, 1.0]
    d = paired_bootstrap_diff(x, x, ["faulty"] * 5, recall_stat, resamples=200)
    assert (d.point, d.lo, d.hi) == (0.0, 0.0, 0.0)
    assert not d.excludes_zero()


def test_paired_bootstrap_detects_dominance():
    x = [1.0] * 10 + [0.0] * 10
    y = [0.0] * 20
    d = paired_bootstrap_diff(x, y, ["faulty"] * 20, recall_stat, resamples=500)
    assert d.point == 0.5
    assert d.excludes_zero()


def test_paired_bootstrap_is_seeded():
    x = [1.0, 0.0, 1.0, 0.0, 1.0, 1.0]
    y = [0.0, 0.0, 1.0, 1.0, 0.0, 1.0]
    s = ["faulty", "faulty", "faulty", "clean", "clean", "clean"]
    a = paired_bootstrap_diff(x, y, s, balanced_stat, resamples=300)
    b = paired_bootstrap_diff(x, y, s, balanced_stat, resamples=300)
    assert a == b


def test_stratified_bootstrap_keeps_strata_sizes():
    # single all 0, multi all 1: every draw keeps delta at exactly 1.
    vals = [0.0, 0.0, 1.0, 1.0, 1.0]
    comp = ["single-vendor"] * 2 + ["multi-vendor"] * 3
    d = stratified_bootstrap(vals, comp, composition_delta_stat, resamples=200)
    assert (d.point, d.lo, d.hi) == (1.0, 1.0, 1.0)
