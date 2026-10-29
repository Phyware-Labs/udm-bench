"""Aggregate statistics for the benchmark report: the four-way detection
breakdown and bootstrap confidence intervals.

Kept deliberately stdlib-only (``random``) so the scoring path carries no
numeric dependency. Bootstrap resampling is seeded, so every reported interval
is reproducible.

Two things live here:

* :func:`detection_breakdown` — the found / missed / false-alarm /
  correct-abstain confusion the single faulty-only scalar hides. This is the
  headline the roadmap (#11) asked for after that scalar misled us twice
  (hallucination artifact, then abstention inflation).
* :func:`bootstrap_ci` / :func:`rate_ci` / :func:`balanced_accuracy_ci` — 95%
  intervals on the rates we report. At n≈23 faulty / 24 clean these intervals
  are *wide*; surfacing that honestly is the entire point.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

# Default bootstrap resample count and CI level. 10 000 resamples is plenty for a
# stable 95% percentile interval at these sample sizes and still runs instantly.
_DEFAULT_RESAMPLES = 10_000
_DEFAULT_CI = 0.95
# Fixed seed so intervals are byte-for-byte reproducible across runs / machines.
_DEFAULT_SEED = 12345


@dataclass(frozen=True)
class DetectionBreakdown:
    """Four-way confusion over one cell's runs.

    Faulty missions split into ``found`` (right fault named) vs ``missed``
    (wrong fault, or no diagnosis submitted). Clean missions split into
    ``correct_abstain`` (declined / said no_fault) vs ``false_alarm`` (claimed a
    fault that was not there).
    """

    found: int = 0
    missed: int = 0
    false_alarm: int = 0
    correct_abstain: int = 0

    @property
    def n_faulty(self) -> int:
        return self.found + self.missed

    @property
    def n_clean(self) -> int:
        return self.false_alarm + self.correct_abstain

    @property
    def recall(self) -> float | None:
        """Faulty recall = found / faulty."""
        return None if self.n_faulty == 0 else self.found / self.n_faulty

    @property
    def specificity(self) -> float | None:
        """Clean specificity = correct_abstain / clean."""
        return None if self.n_clean == 0 else self.correct_abstain / self.n_clean

    @property
    def balanced_accuracy(self) -> float | None:
        """Mean of recall and specificity; None if either stratum is empty."""
        r, s = self.recall, self.specificity
        if r is None or s is None:
            return None
        return (r + s) / 2.0

    def to_dict(self) -> dict[str, object]:
        return {
            "found": self.found,
            "missed": self.missed,
            "false_alarm": self.false_alarm,
            "correct_abstain": self.correct_abstain,
            "n_faulty": self.n_faulty,
            "n_clean": self.n_clean,
        }


def detection_breakdown(
    faulty_correct: list[bool | None], clean_correct: list[bool | None]
) -> DetectionBreakdown:
    """Build the four-way breakdown from per-run correctness flags.

    ``faulty_correct[i]`` is ``root_cause_correct`` for a faulty mission (None is
    treated as a miss — no gradable diagnosis is still a failure to find the
    fault). ``clean_correct[i]`` is ``root_cause_correct`` for a clean mission
    (None treated as a false alarm for symmetry, though clean scoring never
    yields None in practice).
    """
    found = sum(1 for x in faulty_correct if x is True)
    missed = sum(1 for x in faulty_correct if x is not True)
    correct_abstain = sum(1 for x in clean_correct if x is True)
    false_alarm = sum(1 for x in clean_correct if x is not True)
    return DetectionBreakdown(
        found=found,
        missed=missed,
        false_alarm=false_alarm,
        correct_abstain=correct_abstain,
    )


@dataclass(frozen=True)
class ConfidenceInterval:
    point: float
    lo: float
    hi: float
    n: int
    resamples: int = _DEFAULT_RESAMPLES
    ci: float = _DEFAULT_CI

    def to_dict(self) -> dict[str, float | int]:
        return {
            "point": round(self.point, 6),
            "lo": round(self.lo, 6),
            "hi": round(self.hi, 6),
            "n": self.n,
        }


def _percentile(sorted_vals: list[float], q: float) -> float:
    """Linear-interpolated percentile of an already-sorted list, q in [0, 1]."""
    if not sorted_vals:
        raise ValueError("percentile of empty sequence")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo_i = int(pos)
    hi_i = min(lo_i + 1, len(sorted_vals) - 1)
    frac = pos - lo_i
    return sorted_vals[lo_i] * (1 - frac) + sorted_vals[hi_i] * frac


def bootstrap_ci(
    values: list[float],
    *,
    resamples: int = _DEFAULT_RESAMPLES,
    ci: float = _DEFAULT_CI,
    seed: int = _DEFAULT_SEED,
) -> ConfidenceInterval | None:
    """Percentile bootstrap CI for the *mean* of ``values``.

    Returns None for an empty sample. For a single observation the interval
    collapses to the point (a bootstrap cannot manufacture spread from n=1).
    """
    n = len(values)
    if n == 0:
        return None
    point = sum(values) / n
    if n == 1:
        return ConfidenceInterval(point=point, lo=point, hi=point, n=n, resamples=resamples, ci=ci)
    rng = random.Random(seed)
    means: list[float] = []
    for _ in range(resamples):
        s = 0.0
        for _ in range(n):
            s += values[rng.randrange(n)]
        means.append(s / n)
    means.sort()
    tail = (1.0 - ci) / 2.0
    lo = _percentile(means, tail)
    hi = _percentile(means, 1.0 - tail)
    return ConfidenceInterval(point=point, lo=lo, hi=hi, n=n, resamples=resamples, ci=ci)


def rate_ci(
    flags: list[bool | None],
    *,
    treat_none_as: bool = False,
    resamples: int = _DEFAULT_RESAMPLES,
    ci: float = _DEFAULT_CI,
    seed: int = _DEFAULT_SEED,
) -> ConfidenceInterval | None:
    """Bootstrap CI for a success *rate* over boolean flags.

    ``None`` flags are coerced to ``treat_none_as`` (default False) so a
    non-gradable faulty run counts as a miss. Returns None if there are no
    gradable observations.
    """
    values = [1.0 if (x if x is not None else treat_none_as) else 0.0 for x in flags]
    return bootstrap_ci(values, resamples=resamples, ci=ci, seed=seed)


def balanced_accuracy_ci(
    faulty_correct: list[bool | None],
    clean_correct: list[bool | None],
    *,
    resamples: int = _DEFAULT_RESAMPLES,
    ci: float = _DEFAULT_CI,
    seed: int = _DEFAULT_SEED,
) -> ConfidenceInterval | None:
    """Stratified bootstrap CI for balanced accuracy = (recall + specificity) / 2.

    The two strata are resampled *independently* (faulty runs among themselves,
    clean among themselves), mirroring the fixed-by-design mission split, and the
    balanced statistic is recomputed on each pair of resamples. Returns None
    unless both strata are non-empty.
    """
    faulty = [1.0 if x is True else 0.0 for x in faulty_correct]
    clean = [1.0 if x is True else 0.0 for x in clean_correct]
    if not faulty or not clean:
        return None
    nf, nc = len(faulty), len(clean)
    point = (sum(faulty) / nf + sum(clean) / nc) / 2.0
    rng = random.Random(seed)
    stats: list[float] = []
    for _ in range(resamples):
        rf = sum(faulty[rng.randrange(nf)] for _ in range(nf)) / nf
        rc = sum(clean[rng.randrange(nc)] for _ in range(nc)) / nc
        stats.append((rf + rc) / 2.0)
    stats.sort()
    tail = (1.0 - ci) / 2.0
    return ConfidenceInterval(
        point=point,
        lo=_percentile(stats, tail),
        hi=_percentile(stats, 1.0 - tail),
        n=nf + nc,
        resamples=resamples,
        ci=ci,
    )


@dataclass(frozen=True)
class CellStats:
    """The report-ready statistics for one (condition, model, composition) cell."""

    breakdown: DetectionBreakdown
    recall_ci: ConfidenceInterval | None = None
    specificity_ci: ConfidenceInterval | None = None
    balanced_ci: ConfidenceInterval | None = None
    _extra: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        out: dict[str, object] = {"detection_breakdown": self.breakdown.to_dict()}
        out["recall_ci"] = self.recall_ci.to_dict() if self.recall_ci else None
        out["specificity_ci"] = self.specificity_ci.to_dict() if self.specificity_ci else None
        out["balanced_accuracy_ci"] = self.balanced_ci.to_dict() if self.balanced_ci else None
        return out


def cell_stats(
    faulty_correct: list[bool | None],
    clean_correct: list[bool | None],
    *,
    seed: int = _DEFAULT_SEED,
) -> CellStats:
    """Compute the breakdown + all three bootstrap CIs for one cell."""
    return CellStats(
        breakdown=detection_breakdown(faulty_correct, clean_correct),
        recall_ci=rate_ci(faulty_correct, treat_none_as=False, seed=seed),
        specificity_ci=rate_ci(clean_correct, treat_none_as=False, seed=seed),
        balanced_ci=balanced_accuracy_ci(faulty_correct, clean_correct, seed=seed),
    )
