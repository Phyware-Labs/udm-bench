"""Paired significance tests and effect sizes for the Phase 4 analysis.

Every condition runs on the *same* 47 missions, so condition-vs-condition
comparisons are paired by mission. The per-rate bootstrap CIs in
:mod:`scoring.stats` ignore that pairing; the tests here use it, which is the
honest way to ask "is C really better than A on these missions?".

Stdlib-only and seeded, like :mod:`scoring.stats`, so every number reproduces.

* :func:`mcnemar_exact` — exact two-sided McNemar test on discordant pairs.
* :func:`cohens_h` — effect size for a difference of two proportions.
* :func:`paired_bootstrap_diff` — CI on a metric difference, resampling missions
  (within faulty / clean strata) and applying the same draw to both conditions.
* :func:`holm` — Holm-Bonferroni adjustment over a family of p-values.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass

_DEFAULT_RESAMPLES = 10_000
_DEFAULT_SEED = 12345


@dataclass(frozen=True)
class McNemar:
    """Exact McNemar result. ``b`` = x right / y wrong, ``c`` = x wrong / y right."""

    b: int
    c: int
    p: float

    @property
    def n_discordant(self) -> int:
        return self.b + self.c


def mcnemar_exact(x: Sequence[bool], y: Sequence[bool]) -> McNemar:
    """Exact two-sided McNemar test for paired binary outcomes ``x`` vs ``y``.

    Under H0 the discordant pairs split 50/50, so ``min(b, c)`` is binomial
    ``(b + c, 0.5)``; the two-sided p doubles the smaller tail (capped at 1).
    """
    if len(x) != len(y):
        raise ValueError("paired samples must have equal length")
    b = sum(1 for xi, yi in zip(x, y, strict=True) if xi and not yi)
    c = sum(1 for xi, yi in zip(x, y, strict=True) if yi and not xi)
    n = b + c
    if n == 0:
        return McNemar(b=b, c=c, p=1.0)
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2**n
    return McNemar(b=b, c=c, p=min(1.0, 2.0 * tail))


def cohens_h(p1: float, p2: float) -> float:
    """Cohen's h for proportions: ``2·asin(√p1) − 2·asin(√p2)``.

    Rough guide: |h| ≈ 0.2 small, 0.5 medium, 0.8 large.
    """
    return 2.0 * math.asin(math.sqrt(p1)) - 2.0 * math.asin(math.sqrt(p2))


def _percentile(sorted_vals: list[float], q: float) -> float:
    pos = q * (len(sorted_vals) - 1)
    lo_i = int(pos)
    hi_i = min(lo_i + 1, len(sorted_vals) - 1)
    frac = pos - lo_i
    return sorted_vals[lo_i] * (1 - frac) + sorted_vals[hi_i] * frac


@dataclass(frozen=True)
class DiffCI:
    point: float
    lo: float
    hi: float

    def excludes_zero(self) -> bool:
        return self.lo > 0 or self.hi < 0


def paired_bootstrap_diff(
    x: Sequence[float],
    y: Sequence[float],
    strata: Sequence[str],
    stat: Callable[[list[float], list[str]], float],
    *,
    resamples: int = _DEFAULT_RESAMPLES,
    seed: int = _DEFAULT_SEED,
) -> DiffCI:
    """Percentile CI for ``stat(x) − stat(y)`` with missions resampled in pairs.

    Missions are resampled with replacement *within* each stratum (so the
    faulty/clean split stays fixed by design), and the same resampled missions
    are used for both conditions — that shared draw is what makes it paired.
    ``stat`` receives the resampled values and their stratum labels.
    """
    if not (len(x) == len(y) == len(strata)):
        raise ValueError("x, y and strata must have equal length")
    xs, ys, ss = list(x), list(y), list(strata)
    point = stat(xs, ss) - stat(ys, ss)
    diffs = sorted(
        stat([xs[i] for i in idx], rs) - stat([ys[i] for i in idx], rs)
        for idx, rs in _stratified_draws(ss, resamples, seed)
    )
    return DiffCI(point=point, lo=_percentile(diffs, 0.025), hi=_percentile(diffs, 0.975))


def stratified_bootstrap(
    values: Sequence[float],
    strata: Sequence[str],
    stat: Callable[[list[float], list[str]], float],
    *,
    resamples: int = _DEFAULT_RESAMPLES,
    seed: int = _DEFAULT_SEED,
) -> DiffCI:
    """Percentile CI for ``stat(values)``, resampling within each stratum.

    Used for statistics of a *single* condition that contrast strata, e.g. the
    multi-minus-single-vendor delta, where the two mission sets are disjoint.
    """
    vs, ss = list(values), list(strata)
    point = stat(vs, ss)
    draws = sorted(
        stat([vs[i] for i in idx], rs) for idx, rs in _stratified_draws(ss, resamples, seed)
    )
    return DiffCI(point=point, lo=_percentile(draws, 0.025), hi=_percentile(draws, 0.975))


def _stratified_draws(strata: list[str], resamples: int, seed: int):
    """Yield (indices, strata-of-indices) bootstrap draws, stratum sizes fixed."""
    groups: dict[str, list[int]] = {}
    for i, s in enumerate(strata):
        groups.setdefault(s, []).append(i)
    rng = random.Random(seed)
    for _ in range(resamples):
        idx = [g[rng.randrange(len(g))] for g in groups.values() for _ in g]
        yield idx, [strata[i] for i in idx]


def holm(pvalues: Sequence[float]) -> list[float]:
    """Holm-Bonferroni adjusted p-values, returned in the input order."""
    m = len(pvalues)
    order = sorted(range(m), key=lambda i: pvalues[i])
    adjusted = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvalues[i]))
        adjusted[i] = running
    return adjusted


# --- stats usable with paired_bootstrap_diff ---------------------------------


def _mean_where(values: list[float], strata: list[str], label: str) -> float:
    sel = [v for v, s in zip(values, strata, strict=True) if s == label]
    return sum(sel) / len(sel) if sel else 0.0


def recall_stat(values: list[float], strata: list[str]) -> float:
    """Found rate over the ``faulty`` stratum."""
    return _mean_where(values, strata, "faulty")


def specificity_stat(values: list[float], strata: list[str]) -> float:
    """Correct-abstain rate over the ``clean`` stratum."""
    return _mean_where(values, strata, "clean")


def balanced_stat(values: list[float], strata: list[str]) -> float:
    """Mean of recall and specificity."""
    return (recall_stat(values, strata) + specificity_stat(values, strata)) / 2.0


def composition_delta_stat(values: list[float], strata: list[str]) -> float:
    """Multi-vendor minus single-vendor mean (strata labelled by composition)."""
    return _mean_where(values, strata, "multi-vendor") - _mean_where(
        values, strata, "single-vendor"
    )
